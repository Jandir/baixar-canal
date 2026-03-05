#!/usr/bin/env python3
"""
=============================================================================
ESCRIBA: Orquestrador de Download de Legendas do YouTube
=============================================================================

SUMÁRIO DO SCRIPT:
Baixa legendas de todos os vídeos de um canal do YouTube.
O objetivo original é utilizar estas legendas como fontes no NotebookLM,
para alavancar estudos sobre determinado autor ou assunto.

Principais Funcionalidades:
1. Sincronização Incremental: Mantém o registro de progresso primário em
   `lista_[canal].json` (metadados e legendas), operando junto com `historico.txt`.
2. Controle de Ausência: Registra vídeos sem legenda em
   `videos_sem_legenda.txt` para evitar novas tentativas de extração futuramente.
3. Tratamento de Formatção e Limpeza: Baixa e salva `.srt` ou converte para `.txt` limpo.
4. Interface Visual Rica (CLI): Fornece cores semânticas e contadores de tempo e status.

Este script segue as regras de Clean Code Naming para Ekklezia: variáveis
com nomes reveladores, sem aspas enigmáticas e com sufixos tipados
(`_list`, `_set`, `_dict`, `_path`, etc.) para máxima legibilidade.
=============================================================================
"""

import argparse
import glob
import json
import re
import os
import random
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass
from dotenv import load_dotenv

VERSION = "2.1.0"


@dataclass
class SessionConfig:
    """Configuração de sessão montada durante o setup inicial."""
    cwd_path: Path
    channel_dir_name: str
    script_dir_path: Path
    yt_dlp_cmd_list: list[str]
    channel_input_url_or_handle: str
    channel_url: str
    channel_url: str

# Carrega variáveis do .env (localizado no diretório do script)
load_dotenv(Path(__file__).parent / ".env")

# Node.js path para o js-runtime do yt-dlp
# Prioridade: variável NODE_PATH do .env → node encontrado no PATH do sistema
NODE_PATH = os.getenv("NODE_PATH") or shutil.which("node") or ""

# ─── Paleta ANSI ──────────────────────────────────────────────────────────────
RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"

# Cores base
RED    = "\033[0;31m"
GREEN  = "\033[0;32m"
YELLOW = "\033[0;33m"
BLUE   = "\033[0;34m"
WHITE  = "\033[0;37m"

# Bright
BRED   = "\033[1;31m"
BGREEN = "\033[1;32m"
BYELLW = "\033[1;33m"

BCYAN  = "\033[1;36m"
BWHITE = "\033[1;37m"


# ─── Ícones semânticos ──────────────────────────────────────────────────────────
ICON_OK   = f"{BGREEN}✓{RESET}"   # sucesso
ICON_ERR  = f"{BRED}✗{RESET}"    # erro
ICON_WARN = f"{BYELLW}⚠{RESET}"  # aviso
ICON_SKIP = f"{DIM}↷{RESET}"    # pulando
ICON_DL   = f"{BCYAN}▶{RESET}"   # baixando
ICON_WAIT = f"{YELLOW}◌{RESET}"  # aguardando
ICON_INFO = f"{BLUE}•{RESET}"   # informação


# ─── Utilitários de Layout ────────────────────────────────────────────────────

DIV_THIN  = f"{DIM}{'─' * 60}{RESET}"
DIV_THICK = f"{BLUE}{'━' * 60}{RESET}"


# Indentação para sub-status (alinha com o video_id da linha acima)
SUB_INDENT_SPACE = "        "


def _print_formatted(icon: str, message: str, indentation_prefix: str = "  ", end_char: str = "\n") -> None:
    """Print genérico com ícone. indentation_prefix controla a indentação inicial."""
    print(f"{indentation_prefix} {icon}  {message}", end=end_char, flush=True)


def print_ok(message: str, indentation_prefix: str = "  ")  -> None: _print_formatted(ICON_OK,   f"{GREEN}{message}{RESET}", indentation_prefix)
def print_err(message: str, indentation_prefix: str = "  ") -> None: _print_formatted(ICON_ERR,  f"{BRED}{message}{RESET}", indentation_prefix)
def print_warn(message: str, indentation_prefix: str = "  ")-> None: _print_formatted(ICON_WARN, f"{YELLOW}{message}{RESET}", indentation_prefix)
def print_info(message: str, indentation_prefix: str = "  ")-> None: _print_formatted(ICON_INFO, f"{DIM}{message}{RESET}", indentation_prefix)
def print_skip(message: str, indentation_prefix: str = "  ")-> None: _print_formatted(ICON_SKIP, f"{DIM}{message}{RESET}", indentation_prefix)
def print_dl(message: str, indentation_prefix: str = "  ")  -> None: _print_formatted(ICON_DL,   f"{BCYAN}{message}{RESET}", indentation_prefix)


def print_section(section_title: str) -> None:
    """Imprime um separador de seção com título."""
    print(f"\n{DIV_THIN}")
    print(f"  {BOLD}{BWHITE}{section_title}{RESET}")
    print(f"{DIV_THIN}")


def print_header(channel_name: str, script_version: str, execution_mode: str) -> None:
    """Header principal em box drawing."""
    header_line_1 = f" escriba  v{script_version} "
    header_line_2 = f" Canal: {channel_name} "
    header_line_3 = f" Modo:  {execution_mode} "
    max_width = max(len(header_line_1), len(header_line_2), len(header_line_3)) + 2
    horizontal_bar = "━" * max_width
    print()
    print(f"{BCYAN}┏{horizontal_bar}┓{RESET}")
    print(f"{BCYAN}┃{RESET}{BOLD}{header_line_1:<{max_width}}{RESET}{BCYAN}┃{RESET}")
    print(f"{BCYAN}┃{RESET}{DIM}{header_line_2:<{max_width}}{RESET}{BCYAN}┃{RESET}")
    print(f"{BCYAN}┃{RESET}{DIM}{header_line_3:<{max_width}}{RESET}{BCYAN}┃{RESET}")
    print(f"{BCYAN}┗{horizontal_bar}┛{RESET}")
    print()


def print_countdown(seconds_count: int, message: str) -> None:
    """Contagem regressiva com barra visual inline."""
    visual_bar_width = 20
    try:
        for remaining_seconds in range(seconds_count, -1, -1):
            filled_blocks  = int((seconds_count - remaining_seconds) / seconds_count * visual_bar_width) if seconds_count else visual_bar_width
            progress_bar_str = f"{GREEN}{'█' * filled_blocks}{DIM}{'░' * (visual_bar_width - filled_blocks)}{RESET}"
            progress_percentage = int((seconds_count - remaining_seconds) / seconds_count * 100) if seconds_count else 100
            sys.stdout.write(f"\r  {ICON_WAIT}  {message} [{progress_bar_str}] {progress_percentage:>3}%  {DIM}{remaining_seconds}s{RESET}  ")
            sys.stdout.flush()
            if remaining_seconds > 0:
                time.sleep(1)
        sys.stdout.write("\r" + " " * 70 + "\r")
        sys.stdout.flush()
    except KeyboardInterrupt:
        sys.stdout.write("\r" + " " * 70 + "\r")
        sys.stdout.flush()
        raise


# ─── Configuração do Ambiente ─────────────────────────────────────────────────

def setup_environment() -> tuple[Path, list[str]]:
    """
    Valida e retorna:
      - script_dir_path: diretório onde este .py está salvo
      - yt_dlp_cmd_list: comando base para invocar o yt-dlp (python do venv + -m yt_dlp)
    """
    script_dir_path = Path(__file__).parent.resolve()
    python_executable_path = script_dir_path / ".venv" / "bin" / "python3"

    if not python_executable_path.is_file() or not os.access(python_executable_path, os.X_OK):
        print_err(f"Ambiente virtual não encontrado em {python_executable_path}")
        print_info("Execute a instalação das dependências no diretório do script.")
        sys.exit(1)

    yt_dlp_cmd_list = [
        str(python_executable_path), 
        "-m", "yt_dlp", 
        "--remote-components", "ejs:github"
    ]
    if NODE_PATH:
        yt_dlp_cmd_list.extend(["--js-runtimes", f"node:{NODE_PATH}"])
        
    return script_dir_path, yt_dlp_cmd_list


# ─── Cookies ──────────────────────────────────────────────────────────────────

def configure_cookies(cwd_path: Path, script_dir_path: Path, force_refresh_cookies: bool) -> list[str]:
    """
    Retorna os argumentos de cookie para o yt-dlp.
    Se force_refresh_cookies=True, apaga o cookies.txt existente na cwd_path antes de continuar.
    """
    cookies_file_path = cwd_path / "cookies.txt"

    if force_refresh_cookies:
        print_warn("--refresh-cookies ativo. Apagando cache antigo...")
        cookies_file_path.unlink(missing_ok=True)

    def is_valid_cookie_file(path: Path) -> bool:
        if not path.is_file(): return False
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read(100)
                # Verifica se é um arquivo vazio ou se tem a diretiva correta do Netscape
                if not content.strip() or "Netscape" in content or "TRUE" in content:
                    return True
        except Exception:
            pass
        return False

    if is_valid_cookie_file(cookies_file_path):
        print_info(f"Cookies em cache: {cookies_file_path.name}")
        return ["--cookies", str(cookies_file_path)]
    elif cookies_file_path.is_file():
        print_warn(f"Cache de cookies corrompido detectado e removido: {cookies_file_path.name}")
        cookies_file_path.unlink()

    # Fallback: busca no diretório do script
    global_script_cookies_path = script_dir_path / "cookies.txt"
    if global_script_cookies_path.is_file() and not force_refresh_cookies:
        print_info("Cookies do diretório do script.")
        return ["--cookies", str(global_script_cookies_path)]

    print_warn(f"Extraindo cookies do Chrome → {cookies_file_path.name}")
    return ["--cookies-from-browser", "chrome", "--cookies", str(cookies_file_path)]


# ─── Detecção de Idioma ───────────────────────────────────────────────────────

def detect_language(yt_dlp_cmd_list: list[str], cookie_args_list: list[str], channel_url: str) -> str:
    """
    Detecta o idioma nativo do canal pelo primeiro vídeo.
    Retorna string de filtro para --sub-langs (ex: '^pt$').
    """
    print_info("Detectando idioma nativo do canal...")
    
    # Se for um canal e não apontar para um vídeo específico, force /videos
    # para garantir que o yt-dlp baixe a metadata de um vídeo e não de uma aba genérica.
    detect_url = channel_url
    if "watch?v=" not in detect_url and "playlist?list=" not in detect_url:
        if not detect_url.endswith("/videos") and not detect_url.endswith("/shorts") and not detect_url.endswith("/streams"):
            detect_url = detect_url.rstrip("/") + "/videos"

    subprocess_result = subprocess.run(
        yt_dlp_cmd_list + cookie_args_list + ["--print", "language", "--playlist-end", "1", detect_url],
        capture_output=True, text=True
    )
    detected_native_language = subprocess_result.stdout.strip()

    if detected_native_language:
        language_regex_filter = f"^{detected_native_language}$"
        print_ok(f"Idioma detectado automaticamente: {BOLD}{detected_native_language}{RESET}  {DIM}(filtro: {language_regex_filter}){RESET}")
        return language_regex_filter

    print_err("Não foi possível detectar o idioma nativo do canal.")
    print_info("Use --lang (ex: --lang pt) para especificar o idioma.")
    sys.exit(1)


# ─── Listagem de IDs e JSON State ───────────────────────────────────────────────

def get_video_exact_date(video_id: str, yt_dlp_cmd_list: list[str], cookie_args_list: list[str]) -> dict:
    """Extrai a data exata de um único vídeo (usado via ThreadPoolExecutor)."""
    cmd_list = yt_dlp_cmd_list + cookie_args_list + [
        "--dump-json",
        "--skip-download",
        "--ignore-errors",
        "--remote-components", "ejs:github",
        f"https://www.youtube.com/watch?v={video_id}"
    ]
    try:
        process_instance = subprocess.run(cmd_list, capture_output=True, text=True, timeout=30)
        if process_instance.stdout:
            video_json_dict = json.loads(process_instance.stdout)
            upload_date_string = video_json_dict.get("upload_date", "N/A")
            if upload_date_string and len(upload_date_string) == 8:
                upload_date_string = f"{upload_date_string[:4]}-{upload_date_string[4:6]}-{upload_date_string[6:]}"
            return {"id": video_id, "date": upload_date_string, "title": video_json_dict.get("title", "N/A")}
    except Exception:
        pass
    return {"id": video_id, "date": "N/A", "title": "N/A"}


def generate_fast_list_json(
    yt_dlp_cmd_list: list[str],
    cookie_args_list: list[str],
    channel_url: str,
    max_workers_count: int = 20
) -> list[dict]:
    """Descobre IDs nativos via --flat-playlist e busca datas em paralelo, montando a base de rastreamento JSON."""
    print_info(f"Fase 1: Descoberta de IDs ({BOLD}{channel_url}{RESET})...")
    discovery_cmd_list = yt_dlp_cmd_list + cookie_args_list + [
        "--flat-playlist",
        "--dump-json",
        "--ignore-errors",
        "--remote-components", "ejs:github",
        channel_url
    ]
    
    raw_video_list = []
    try:
        discovery_process = subprocess.Popen(discovery_cmd_list, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        for line_content in discovery_process.stdout:
            try:
                obj = json.loads(line_content.strip())
                if obj.get("id"):
                    raw_video_list.append({"id": obj["id"], "title": obj.get("title", "N/A")})
                    sys.stdout.write(f"\r  {ICON_WAIT}  {CYAN}IDs encontrados: {len(raw_video_list)}{RESET}")
                    sys.stdout.flush()
            except: continue
        discovery_process.wait()
    except Exception as error_msg:
        print_warn(f"\nErro na descoberta: {error_msg}")
        return []
        
    if not raw_video_list:
        print_warn("\nNenhum vídeo encontrado para mapear state JSON.")
        return []
        
    total_videos_count = len(raw_video_list)
    final_metadata_list = []
    print_info(f"\nFase 2: Extração de Metadados em Paralelo ({BOLD}{max_workers_count} threads{RESET})...")
    
    start_time_float = time.time()
    with ThreadPoolExecutor(max_workers=max_workers_count) as executor_instance:
        future_tasks_dict = {
            executor_instance.submit(get_video_exact_date, video_dict["id"], yt_dlp_cmd_list, cookie_args_list): video_dict 
            for video_dict in raw_video_list
        }
        for future_task in as_completed(future_tasks_dict):
            result_dict = future_task.result()
            final_metadata_list.append({
                "video_id": result_dict["id"],
                "publish_date": result_dict["date"],
                "title": result_dict["title"],
                "subtitle_downloaded": False,
                "info_downloaded": False,
                "has_no_subtitle": False
            })
            processed_count = len(final_metadata_list)
            elapsed_time_float = time.time() - start_time_float
            items_per_second_float = processed_count / elapsed_time_float if elapsed_time_float > 0 else 0
            remaining_seconds = int((total_videos_count - processed_count) / items_per_second_float) if items_per_second_float > 0 else 0
            eta_min = remaining_seconds // 60
            eta_sec = remaining_seconds % 60
            eta_str = f"{eta_min}m {eta_sec}s" if eta_min > 0 else f"{eta_sec}s"
            
            sys.stdout.write(
                f"\r  {ICON_DL}  {GREEN}Processado: {processed_count}/{total_videos_count}{RESET} "
                f"({items_per_second_float:.1f} video/s) "
                f"{YELLOW}ETA: {eta_str}{RESET}    "
            )
            sys.stdout.flush()
            
    # Restaurar ordem cronológica invertida da flat playlist
    id_to_order_dict = {v["id"]: i for i, v in enumerate(raw_video_list)}
    final_metadata_list.sort(key=lambda x: id_to_order_dict.get(x["video_id"], 999999))
    print_ok(f"\nMapeamento completo em {int(time.time() - start_time_float)} segundos.")
    return final_metadata_list


def get_latest_json_path(cwd_path: Path, channel_name_safe: str | None = None) -> Path | None:
    if channel_name_safe:
        specific_path = cwd_path / f"lista_{channel_name_safe}.json"
        if specific_path.exists():
            return specific_path
        return None
            
    json_files_list = glob.glob(str(cwd_path / "lista_*.json"))
    if not json_files_list:
        return None
    return Path(max(json_files_list, key=os.path.getmtime))


def load_or_create_channel_state(
    cwd_path: Path, 
    yt_dlp_cmd_list: list[str], 
    cookie_args_list: list[str], 
    channel_url: str
) -> tuple[Path | None, list[dict]]:
    """Carrega o banco de dados JSON do canal. Se não encontrado, mapeia o canal e gera on-the-fly."""
    
    channel_name_safe = None
    match = re.search(r"@([A-Za-z0-9_-]+)", channel_url)
    if match:
        channel_name_safe = match.group(1)
        
    latest_json_path = get_latest_json_path(cwd_path, channel_name_safe)
    if latest_json_path:
        print_info(f"Usando JSON state database: {BOLD}{latest_json_path.name}{RESET}")
        try:
            with open(latest_json_path, "r", encoding="utf-8") as file_descriptor:
                raw_data_list = json.load(file_descriptor)
                # Migração on-the-fly para o novo schema, suportando listas antigas
                for item in raw_data_list:
                    if "subtitle_downloaded" not in item:
                        item["subtitle_downloaded"] = False
                    if "video_id" not in item and "id" in item:
                        item["video_id"] = item.pop("id")
                    if "publish_date" not in item and "date" in item:
                        item["publish_date"] = item.pop("date")
                    if "info_downloaded" not in item:
                        item["info_downloaded"] = False
                    if "has_no_subtitle" not in item:
                        item["has_no_subtitle"] = False
                return latest_json_path, raw_data_list
        except Exception as error_msg:
            print_warn(f"Erro ao ler JSON de estado: {error_msg}")
            
    # Arquivo não existe ou erro. Cria on-the-fly:
    if not latest_json_path:
        print_info(f"State JSON {BOLD}não detectado{RESET}. Criando infraestrutura e cache de alta velocidade...")
        
        if not channel_name_safe:
            channel_name_safe = "canal"
             
        latest_json_path = cwd_path / f"lista_{channel_name_safe}.json"
        raw_data_list = generate_fast_list_json(yt_dlp_cmd_list, cookie_args_list, channel_url)
        
        if not raw_data_list:
            return None, []

    # Aqui independente se carregou do disco ou acabou de gerar: executa a auto-migração
    was_migrated = auto_migrate_legacy_files(cwd_path, raw_data_list)

    if not latest_json_path.exists() or was_migrated:
        save_channel_state_json(latest_json_path, raw_data_list)
        if not latest_json_path.exists():
            print_ok(f"State database gravado em: {BOLD}{latest_json_path.name}{RESET}")

    return latest_json_path, raw_data_list


def save_channel_state_json(json_path: Path | None, state_list: list[dict]):
    """Atualiza atomicamente arquivo JSON em disco caso tenhamos modificado o tracker de download."""
    if not json_path or not state_list:
        return
    temp_path = json_path.with_suffix(".tmp")
    try:
        with open(temp_path, "w", encoding="utf-8") as file_descriptor:
            json.dump(state_list, file_descriptor, indent=4, ensure_ascii=False)
        temp_path.replace(json_path)
    except Exception as e:
        print_warn(f"Ignorando erro ao salvar JSON de state: {e}")


def auto_migrate_legacy_files(cwd_path: Path, state_list: list[dict]) -> bool:
    """
    Se existirem arquivos texto antigos do projeto (historico.txt, historico-info.txt, videos_sem_legenda.txt),
    lê e consolida os dados no state_list em memória, e depois os renomeia para .bak para não repetir.
    Retorna True se alguma modificação nos dicionários foi feita.
    """
    historico_ids = set()
    historico_path = cwd_path / "historico.txt"
    if historico_path.is_file():
        with open(historico_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("youtube "): historico_ids.add(line.strip()[len("youtube "):])

    info_ids = set()
    info_path = cwd_path / "historico-info.txt"
    if info_path.is_file():
        with open(info_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("youtube "): info_ids.add(line.strip()[len("youtube "):])

    no_sub_ids = set()
    no_sub_path = cwd_path / "videos_sem_legenda.txt"
    if no_sub_path.is_file():
        with open(no_sub_path, "r", encoding="utf-8") as f:
            for line in f:
                if "watch?v=" in line:
                    vid = line.strip().split("watch?v=")[-1].strip()
                    if vid: no_sub_ids.add(vid)

    if not historico_ids and not info_ids and not no_sub_ids:
        return False

    migrated_count = 0
    for item in state_list:
        video_id = item.get("video_id")
        if not video_id: continue

        if video_id in historico_ids and not item.get("subtitle_downloaded"):
            item["subtitle_downloaded"] = True
            migrated_count += 1
            
        if video_id in info_ids and not item.get("info_downloaded"):
            item["info_downloaded"] = True
            migrated_count += 1
            
        if video_id in no_sub_ids and not item.get("has_no_subtitle"):
            item["has_no_subtitle"] = True
            migrated_count += 1

    if historico_path.is_file(): historico_path.rename(historico_path.with_suffix(".txt.bak"))
    if info_path.is_file(): info_path.rename(info_path.with_suffix(".txt.bak"))
    if no_sub_path.is_file(): no_sub_path.rename(no_sub_path.with_suffix(".txt.bak"))

    if migrated_count > 0:
        print_ok(f"Migração de arquivos de log textuais (legacy) detectada e concluída ({migrated_count} updates no JSON).")
    return True


def filter_state_list(
    full_state_list: list[dict], 
    date_limit_filter: str
) -> list[dict]:
    """
    Retorna a lista filtrada contendo apenas os ponteiros dos dicts onde os requisitos
    se encaixam no filtro de datas (se houver).
    Como python passa dicionários por referência, alterar a lista clonada altera o state orignal também.
    """
    if not full_state_list:
        return []

    # Aplica filtro de data (quando -d foi passado)
    if date_limit_filter:
        try:
            from yt_dlp.utils import DateRange
            parsed_date_str = DateRange.day(date_limit_filter).start
            if parsed_date_str:
                date_limit_filter = parsed_date_str.replace("-", "")
        except Exception:
            pass  # Fallback to string comparison
            
        filtered_list = []
        for v_dict in full_state_list:
            d_str = v_dict.get("publish_date", "N/A")
            if d_str and d_str != "N/A":
                # Remove hifens para comparação (YYYYMMDD ou len 8)
                d_str_clean = d_str.replace("-", "")
                if d_str_clean >= date_limit_filter:
                    filtered_list.append(v_dict)
        return filtered_list
        
    return list(full_state_list)


# ─── Pós-processamento de Legendas ────────────────────────────────────────────

SUBTITLE_INDEX_REGEX_PATTERN = re.compile(r"^\d+$")
SUBTITLE_TIMESTAMP_REGEX_PATTERN = re.compile(
    r"^\d{2}:\d{2}:\d{2}[.,]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[.,]\d{3}"
)


def srt_to_txt(srt_file_path: Path) -> Path:
    """
    Converte um arquivo .srt em .txt limpo (sem timestamps, sem numeração).
    Deduplica linhas roll-up consecutivas geradas pelo YouTube.
    Retorna o caminho do .txt gerado.
    """
    cleaned_lines_list: list[str] = []
    previous_subtitle_line = ""

    with open(srt_file_path, encoding="utf-8", errors="replace") as file_descriptor:
        for raw_subtitle_line in file_descriptor:
            raw_subtitle_line = raw_subtitle_line.strip()
            # Pula linhas vazias, índices numéricos e timestamps
            if not raw_subtitle_line or SUBTITLE_INDEX_REGEX_PATTERN.match(raw_subtitle_line) or SUBTITLE_TIMESTAMP_REGEX_PATTERN.match(raw_subtitle_line):
                continue
            # Remove tags HTML/XML (<i>, </i>, <font> etc.)
            cleaned_subtitle_line = re.sub(r"<[^>]+>", "", raw_subtitle_line).strip()
            if not cleaned_subtitle_line:
                continue
            # Deduplica roll-up: pula linha se idêntica à anterior
            if cleaned_subtitle_line == previous_subtitle_line:
                continue
            cleaned_lines_list.append(cleaned_subtitle_line)
            previous_subtitle_line = cleaned_subtitle_line

    txt_file_path = srt_file_path.with_suffix(".txt")
    with open(txt_file_path, "w", encoding="utf-8") as file_descriptor:
        file_descriptor.write("\n".join(cleaned_lines_list) + "\n")

    return txt_file_path


def cleanup_subtitles(
    cwd_path: Path,
    channel_dir_name: str,
    video_id: str,
    convert_srt_to_txt: bool = False,
    flag_keep_srt: bool = False,
) -> bool:
    """
    Remove variações duplicadas de legenda geradas pelo yt-dlp,
    mantendo apenas o arquivo com o menor nome (ex: prefere 'pt' sobre 'pt-BR').
    Renomeia de '.pt.srt' para '-pt.srt'.
    Se convert_srt_to_txt=True, converte para .txt e opcionalmente remove o .srt.
    Retorna True se processou alguma legenda, caso contrário False.
    """
    subtitle_file_pattern = str(cwd_path / f"{channel_dir_name}-{video_id}*.srt")
    matching_subtitle_files_list = glob.glob(subtitle_file_pattern)

    if not matching_subtitle_files_list:
        return False

    if len(matching_subtitle_files_list) > 1:
        print_warn(f"{len(matching_subtitle_files_list)} variações de legenda detectadas — mantendo apenas uma.")
        shortest_subtitle_file_path = min(matching_subtitle_files_list, key=len)
        for iterable_file_path in matching_subtitle_files_list:
            if iterable_file_path != shortest_subtitle_file_path:
                os.unlink(iterable_file_path)
        target_subtitle_file_path = Path(shortest_subtitle_file_path)
    else:
        target_subtitle_file_path = Path(matching_subtitle_files_list[0])

    # Renomear: FOLDER-ID.lang.srt → FOLDER-ID-lang.srt
    base_prefix_string = f"{channel_dir_name}-{video_id}"
    language_suffix_extracted = target_subtitle_file_path.name[len(base_prefix_string):]

    if language_suffix_extracted.startswith(".") and target_subtitle_file_path.suffix == ".srt" and language_suffix_extracted.count(".") >= 2:
        new_language_suffix = "-" + language_suffix_extracted.lstrip(".")
        new_subtitle_filename_path = target_subtitle_file_path.parent / f"{base_prefix_string}{new_language_suffix}"
        target_subtitle_file_path.rename(new_subtitle_filename_path)
        target_subtitle_file_path = new_subtitle_filename_path

    # Conversão SRT → TXT limpo
    if convert_srt_to_txt:
        txt_file_path = srt_to_txt(target_subtitle_file_path)
        print_info(f"Texto salvo: {DIM}{txt_file_path.name}{RESET}")
        if not flag_keep_srt:
            target_subtitle_file_path.unlink()
        else:
            print_info(f"SRT mantido: {DIM}{target_subtitle_file_path.name}{RESET}")
    else:
        print_info(f"Legenda salva: {DIM}{target_subtitle_file_path.name}{RESET}")

    return True


# ─── Download Individual ──────────────────────────────────────────────────────

def download_video(
    yt_dlp_cmd_list: list[str],
    cookie_args_list: list[str],
    video_id: str,
    language_opt_string: str,
    channel_dir_name: str,
    audio_only_flag: bool,
    output_dir_path: Path | None = None,
) -> int:
    """
    Executa o yt-dlp para baixar legendas ou áudio de um único vídeo.
    Retorna o exit code.
    """
    output_template_string = f"{channel_dir_name}-%(id)s"
    if audio_only_flag:
        output_template_string += ".%(ext)s"
        
    if output_dir_path:
        output_template_string = str(output_dir_path / output_template_string)

    download_cmd_list = (
        yt_dlp_cmd_list
        + ["--js-runtimes", f"node:{NODE_PATH}"]
        + ["--ignore-no-formats-error"]
        + ["--write-info-json"]
        + (["-f", "ba[ext=webm]"] if audio_only_flag else ["--skip-download", "--write-auto-sub", "--convert-subs", "srt"])
        + cookie_args_list
        + (["--sub-langs", language_opt_string] if not audio_only_flag else [])
        + ["-o", output_template_string]
        + [f"https://www.youtube.com/watch?v={video_id}"]
    )

    subprocess_instance = subprocess.Popen(download_cmd_list)
    try:
        subprocess_instance.wait()
    except KeyboardInterrupt:
        subprocess_instance.terminate()
        try:
            subprocess_instance.wait(timeout=5)
        except subprocess.TimeoutExpired:
            subprocess_instance.kill()
        raise  # repropaga para o handler principal
    return subprocess_instance.returncode


# ─── Argparse ─────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    cli_parser = argparse.ArgumentParser(
        prog="escriba.py",
        description=(
            "Baixa legendas de todos os vídeos de um canal ou playlist do YouTube.\n"
            f"Versão: {VERSION}\n\n"
            "Padrão de nome dos arquivos: [NOME_DA_PASTA]-[ID_VIDEO]-[LANG].srt\n"
            "Vídeos que não contêm legendas são registrados em 'videos_sem_legenda.txt'\n"
            "na pasta do canal e serão automaticamente ignorados nas próximas execuções."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    cli_parser.add_argument("canal", help="Canal, playlist, vídeo ou URL (ex: @Canal, VIDEO_ID, URL de vídeo/playlist)")
    cli_parser.add_argument("-l", "--lang", default="", metavar="LANG",
                        help="Idioma das legendas (ex: pt, en). Padrão: idioma nativo do canal")
    cli_parser.add_argument("-a", "--audio-only", action="store_true",
                        help="Baixa APENAS o áudio do vídeo (webm/opus), sem legendas")
    cli_parser.add_argument("-t", "--txt", action="store_true",
                        help="Exporta legendas como .txt limpo (sem timestamps). Remove o .srt por padrão")
    cli_parser.add_argument("--keep-srt", action="store_true",
                        help="Mantém o arquivo .srt ao usar --txt (gera ambos .srt e .txt)")
    cli_parser.add_argument("--audio-fallback", action="store_true",
                        help="Baixa o áudio quando a legenda não está disponível (padrão: apenas registra)")
    cli_parser.add_argument("-d", "--date", default="", metavar="DATA",
                        help="Data limite (posterior a). Formato: YYYYMMDD (ex: 20260101)")
    cli_parser.add_argument("-rc", "--refresh-cookies", action="store_true",
                        help="Força a extração de novos cookies do Chrome (apaga cookies.txt existente)")
    cli_parser.add_argument("-f", "--fast", action="store_true",
                        help="Modo rápido: pula o tempo de espera entre downloads")
    cli_parser.add_argument("-v", "--version", action="version", version=f"Versão: {VERSION}")
    return cli_parser.parse_args()


# ─── Main ─────────────────────────────────────────────────────────────────────

# Regex para detectar YouTube video ID (exatamente 11 chars alfanuméricos + _ e -)
VIDEO_ID_REGEX_PATTERN = re.compile(r"^[A-Za-z0-9_-]{11}$")


def parse_input_type(channel_input_string: str) -> tuple[str, str, str]:
    """
    Classifica a entrada do usuário e retorna (channel_url_string, input_type_string, video_id_string | "").
    input_type_string: 'video', 'playlist', ou 'channel'
    """
    # URL completa de vídeo
    if "watch?v=" in channel_input_string or "youtu.be/" in channel_input_string:
        channel_url_string = channel_input_string if channel_input_string.startswith("http") else f"https://www.youtube.com/watch?v={channel_input_string}"
        # Extrair video ID da URL
        regex_match_result = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})", channel_url_string)
        video_id = regex_match_result.group(1) if regex_match_result else ""
        return channel_url_string, "video", video_id

    # ID avulso de vídeo (11 caracteres)
    if VIDEO_ID_REGEX_PATTERN.match(channel_input_string):
        channel_url_string = f"https://www.youtube.com/watch?v={channel_input_string}"
        return channel_url_string, "video", channel_input_string

    # Playlist
    if "playlist?list=" in channel_input_string:
        channel_url_string = channel_input_string if channel_input_string.startswith("http") else f"https://www.youtube.com/{channel_input_string}"
        return channel_url_string, "playlist", ""

    # Canal (handle ou URL)
    channel_url_string = channel_input_string if channel_input_string.startswith("http") else f"https://www.youtube.com/{channel_input_string}"
    return channel_url_string, "channel", ""


def setup_session(cli_args: argparse.Namespace) -> SessionConfig:
    """
    Etapa 1: monta a configuração da sessão, imprime header e seção de config.
    """
    cwd_path = Path.cwd()
    channel_dir_name = cwd_path.name
    script_dir_path, yt_dlp_cmd_list = setup_environment()

    # Classificar entrada
    channel_input_string = cli_args.canal
    channel_url_string, input_type_string, single_video_id = parse_input_type(channel_input_string)

    # Modo de operação para o header
    file_format_string = "TXT" if cli_args.txt else "SRT"
    execution_mode_label = "Áudio" if cli_args.audio_only else f"Legendas/{file_format_string} ({cli_args.lang or 'auto'})"
    if cli_args.date:
        execution_mode_label += f"  ·  a partir de {cli_args.date}"
    if cli_args.fast:
        execution_mode_label += "  ·  rápido"
    print_header(channel_input_string, VERSION, execution_mode_label)

    return SessionConfig(
        cwd_path=cwd_path,
        channel_dir_name=channel_dir_name,
        script_dir_path=script_dir_path,
        yt_dlp_cmd_list=yt_dlp_cmd_list,
        channel_input_url_or_handle=channel_input_string,
        channel_url=channel_url_string,
    )


def init_auth_and_language(
    session_config: SessionConfig, language_argument_string: str, force_refresh_cookies_flag: bool
) -> tuple[list[str], str]:
    """
    Etapa 2: configura cookies e detecta/define o idioma.
    Retorna (cookie_args_list, language_opt_string).
    """
    print_section("Autenticação")
    cookie_args_list = configure_cookies(session_config.cwd_path, session_config.script_dir_path, force_refresh_cookies_flag)

    print_section("Idioma")
    language_opt_string = language_argument_string if language_argument_string else detect_language(session_config.yt_dlp_cmd_list, cookie_args_list, session_config.channel_url)
    if language_argument_string:
        print_ok(f"Idioma definido pelo usuário: {BOLD}{language_opt_string}{RESET}")

    # Após a 1ª chamada ao yt-dlp (detect_language ou skip), o cookies.txt já foi criado.
    # Recarregar para evitar extrair cookies do Chrome em cada vídeo.
    if "--cookies-from-browser" in cookie_args_list:
        cookie_args_list = configure_cookies(session_config.cwd_path, session_config.script_dir_path, False)
        print_info("Cookies salvos em cache — reaproveitando para os downloads.")

    return cookie_args_list, language_opt_string


def process_videos(
    session_config: SessionConfig,
    cookie_args_list: list[str],
    language_opt_string: str,
    cli_args: argparse.Namespace,
) -> tuple[int, int, int, int]:
    """
    Etapa 3: itera a base de estado JSON e logs legados em disco, executando
    filtros incrementais em memória via sets O(1) e processando as requisições yt-dlp.
    Retorna os contadores numéricos formatados para o summary da Etapa 4.
    """
    # Detectar se é vídeo avulso
    _, input_type_string, single_video_id = parse_input_type(session_config.channel_input_url_or_handle)

    if input_type_string == "video" and single_video_id:
        print_section("Vídeo Avulso")
        json_state_path = None
        full_state_list = None
        working_state_list = [{"video_id": single_video_id, "publish_date": "N/A", "title": "Avulso", "subtitle_downloaded": False}]
        print_info(f"Processando vídeo: {BOLD}{single_video_id}{RESET}")
    else:
        print_section("Listagem de Vídeos e Tracking State")
        json_state_path, full_state_list = load_or_create_channel_state(
            session_config.cwd_path, session_config.yt_dlp_cmd_list, cookie_args_list, session_config.channel_url
        )
        working_state_list = filter_state_list(full_state_list, cli_args.date)

    if not working_state_list:
        print_err("Nenhum vídeo retornado pela listagem ou filtro.")
        sys.exit(1)

    info_downloaded_count = sum(1 for v in working_state_list if v.get("info_downloaded"))
    no_subtitle_count = sum(1 for v in working_state_list if v.get("has_no_subtitle"))
    print_info(f"Histórico: {info_downloaded_count} metadados no JSON · {no_subtitle_count} sem legenda")

    # Contadores de sessão
    skipped_videos_count = downloaded_videos_count = error_videos_count = 0
    total_videos_count = len(working_state_list)

    print_section(f"Download  {DIM}(0/{total_videos_count}){RESET}")

    # ─── Loop principal ────────────────────────────────────────────────────────
    was_interrupted = False
    try:
        for loop_iteration_idx, video_dict in enumerate(working_state_list, start=1):
            video_id = video_dict["video_id"]
            indentation_prefix = f"  {BLUE}[{loop_iteration_idx:>{len(str(total_videos_count))}}/{total_videos_count}]{RESET}"

            # 1. Verificação instantânea no JSON de estado do canal
            if video_dict.get("subtitle_downloaded") and not cli_args.audio_only:
                skipped_videos_count += 1
                print_skip(f"{video_id}  {DIM}legenda já registrada no state JSON{RESET}", indentation_prefix)
                continue

            if video_dict.get("has_no_subtitle") and not cli_args.audio_only:
                skipped_videos_count += 1
                print_skip(f"{video_id}  {DIM}marcado como sem legenda no JSON{RESET}", indentation_prefix)
                continue

            # Verificação dupla no dataset
            is_video_in_info = video_dict.get("info_downloaded", False)

            # Verificação por arquivos em disco (caso o histórico esteja dessincronizado)
            info_json_file_path = session_config.cwd_path / f"{session_config.channel_dir_name}-{video_id}.info.json"
            is_info_json_present = info_json_file_path.is_file()
            is_srt_file_present = bool(glob.glob(str(session_config.cwd_path / f"{session_config.channel_dir_name}-{video_id}*.srt")))
            is_txt_file_present = bool(glob.glob(str(session_config.cwd_path / f"{session_config.channel_dir_name}-{video_id}*.txt")))
            
            if is_info_json_present and (is_srt_file_present or is_txt_file_present):
                skipped_videos_count += 1
                
                video_dict["info_downloaded"] = True
                video_dict["subtitle_downloaded"] = True
                save_channel_state_json(json_state_path, full_state_list)
                
                print_skip(f"{video_id}  {DIM}arquivos já presentes no disco{RESET}", indentation_prefix)
                continue

            if is_info_json_present and is_video_in_info and cli_args.audio_only:
                 # Just an FYI tracking logic to support future iterations
                 pass

            execution_mode_string = "ÁUDIO" if cli_args.audio_only else f"legenda/{language_opt_string}"
            print_dl(f"{video_id}{RESET}  {DIM}{execution_mode_string}{RESET}", indentation_prefix)

            download_exit_code = download_video(
                yt_dlp_cmd_list=session_config.yt_dlp_cmd_list,
                cookie_args_list=cookie_args_list,
                video_id=video_id,
                language_opt_string=language_opt_string,
                channel_dir_name=session_config.channel_dir_name,
                audio_only_flag=cli_args.audio_only,
            )

            if download_exit_code == 0:
                video_dict["info_downloaded"] = True
                save_channel_state_json(json_state_path, full_state_list)

                has_downloaded_subtitle_flag = True
                if not cli_args.audio_only:
                    has_downloaded_subtitle_flag = cleanup_subtitles(
                        session_config.cwd_path, session_config.channel_dir_name, video_id,
                        convert_srt_to_txt=cli_args.txt, flag_keep_srt=cli_args.keep_srt,
                    )

                if not has_downloaded_subtitle_flag:
                    if cli_args.audio_fallback:
                        print_warn(f"sem legenda — baixando áudio fallback", SUB_INDENT_SPACE)
                        
                        fallback_audios_dir_path = session_config.cwd_path / "audios"
                        fallback_audios_dir_path.mkdir(exist_ok=True)
                        
                        audio_fallback_exit_code = download_video(
                            yt_dlp_cmd_list=session_config.yt_dlp_cmd_list,
                            cookie_args_list=cookie_args_list,
                            video_id=video_id,
                            language_opt_string=language_opt_string,
                            channel_dir_name=session_config.channel_dir_name,
                            audio_only_flag=True,
                            output_dir_path=fallback_audios_dir_path,
                        )
                        
                        if audio_fallback_exit_code == 0:
                            print_ok(f"áudio fallback salvo em audios/", SUB_INDENT_SPACE)
                        else:
                            print_err(f"falha ao baixar áudio fallback", SUB_INDENT_SPACE)
                    else:
                        print_warn(f"sem legenda — pulando", SUB_INDENT_SPACE)

                    skipped_videos_count += 1

                    # Só marca como "sem legenda" se o vídeo tem mais de 30 dias
                    is_old_enough_flag = True  # fallback: marca se não conseguir ler a data
                    if info_json_file_path.is_file():
                        try:
                            with open(info_json_file_path) as file_descriptor:
                                upload_date_string = json.load(file_descriptor).get("upload_date", "")
                            if upload_date_string:
                                upload_datetime_object = datetime.strptime(upload_date_string, "%Y%m%d")
                                days_ago_count = (datetime.now() - upload_datetime_object).days
                                is_old_enough_flag = days_ago_count > 30
                        except (json.JSONDecodeError, ValueError):
                            pass

                    if is_old_enough_flag:
                        video_dict["has_no_subtitle"] = True
                        save_channel_state_json(json_state_path, full_state_list)
                    else:
                        print_info(f"vídeo recente ({days_ago_count}d) — não marcado como sem legenda", SUB_INDENT_SPACE)

                    if not cli_args.fast:
                        print_countdown(1, "Aguardando")
                else:
                    downloaded_videos_count += 1
                    
                    # Marcar o estado JSON se baixamos a legenda
                    if not cli_args.audio_only and has_downloaded_subtitle_flag:
                        video_dict["subtitle_downloaded"] = True
                        save_channel_state_json(json_state_path, full_state_list)
                        
                    if not cli_args.fast:
                        sleep_duration_seconds = random.randint(1, 5)
                        print_countdown(sleep_duration_seconds, "Aguardando")
                    else:
                        print_ok("ok", SUB_INDENT_SPACE)
            else:
                error_videos_count += 1
                print_err(f"falha (código {download_exit_code}) — possível bloqueio 429", SUB_INDENT_SPACE)
                if not cli_args.fast:
                    print_countdown(300, "Resfriamento")
                print_info("Retomando...")

    except KeyboardInterrupt:
        print()
        print_warn(f"Processamento interrompido. {DIM}Gerando resumo parcial...{RESET}")
        was_interrupted = True

    return downloaded_videos_count, skipped_videos_count, error_videos_count, total_videos_count, was_interrupted


def print_summary(downloaded_videos_count: int, skipped_videos_count: int, error_videos_count: int, total_videos_count: int) -> None:
    """Etapa 4: imprime o resumo final da sessão."""
    print(f"\n{DIV_THICK}")
    print(f"  {BOLD}{BWHITE}Sessão concluída{RESET}")
    print(f"{DIV_THICK}")
    print(f"  {ICON_OK}  Baixados  : {BGREEN}{downloaded_videos_count}{RESET}")
    print(f"  {ICON_SKIP}  Pulados   : {DIM}{skipped_videos_count}{RESET}")
    if error_videos_count:
        print(f"  {ICON_ERR}  Erros     : {BRED}{error_videos_count}{RESET}")
    print(f"  {ICON_INFO}  Total fila : {total_videos_count}")
    print()


def main() -> None:
    cli_args = parse_args()
    session_config = setup_session(cli_args)
    cookie_args_list, language_opt_string = init_auth_and_language(
        session_config, cli_args.lang, cli_args.refresh_cookies
    )
    downloaded_videos_count, skipped_videos_count, error_videos_count, total_videos_count, was_interrupted = process_videos(
        session_config, cookie_args_list, language_opt_string, cli_args
    )
    print_summary(downloaded_videos_count, skipped_videos_count, error_videos_count, total_videos_count)
    if was_interrupted:
        sys.exit(130)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        print_warn(f"Interrompido pelo usuário (Ctrl+C).  {DIM}Saindo...{RESET}")
        sys.exit(130)  # Código 130 = SIGINT (padrão Unix)
