#!/usr/bin/env python3
"""
Script: baixar-canal.py
Descrição: Baixa legendas de todos os vídeos de um canal do YouTube.
           O objetivo original é utilizar estas legendas como fontes no NotebookLM,
           para alavancar estudos sobre determinado autor ou assunto.
"""

import argparse
import glob
import json
import os
import random
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

VERSION = "1.9.0"

# Node.js path para o js-runtime do yt-dlp
NODE_PATH = "/Users/jandirp/.nvm/versions/node/v22.16.0/bin/node"

# ─── Paleta ANSI ──────────────────────────────────────────────────────────────
RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"

# Cores base
RED    = "\033[0;31m"
GREEN  = "\033[0;32m"
YELLOW = "\033[0;33m"
BLUE   = "\033[0;34m"
CYAN   = "\033[0;36m"
WHITE  = "\033[0;37m"

# Bright
BRED   = "\033[1;31m"
BGREEN = "\033[1;32m"
BYELLW = "\033[1;33m"
BBLUE  = "\033[1;34m"
BCYAN  = "\033[1;36m"
BWHITE = "\033[1;37m"

NC = RESET  # alias para compatibilidade

# ─── Ícones semânticos ──────────────────────────────────────────────────────────
OK   = f"{BGREEN}✓{RESET}"   # sucesso
ERR  = f"{BRED}✗{RESET}"    # erro
WARN = f"{BYELLW}⚠{RESET}"  # aviso
SKIP = f"{DIM}↷{RESET}"    # pulando
DL   = f"{BCYAN}▶{RESET}"   # baixando
WAIT = f"{YELLOW}◌{RESET}"  # aguardando
INFO = f"{BLUE}•{RESET}"   # informação


# ─── Utilitários de Layout ────────────────────────────────────────────────────

DIV_THIN  = f"{DIM}{'─' * 60}{RESET}"
DIV_THICK = f"{BLUE}{'━' * 60}{RESET}"


def _p(icon: str, msg: str, end: str = "\n") -> None:
    """Print genérico com ícone."""
    print(f"  {icon}  {msg}", end=end, flush=True)


def ok(msg: str)  -> None: _p(OK,   f"{GREEN}{msg}{RESET}")
def err(msg: str) -> None: _p(ERR,  f"{BRED}{msg}{RESET}")
def warn(msg: str)-> None: _p(WARN, f"{YELLOW}{msg}{RESET}")
def info(msg: str)-> None: _p(INFO, f"{DIM}{msg}{RESET}")
def skip(msg: str)-> None: _p(SKIP, f"{DIM}{msg}{RESET}")
def dl(msg: str)  -> None: _p(DL,   f"{BCYAN}{msg}{RESET}")


def section(title: str) -> None:
    """Imprime um separador de seção com título."""
    print(f"\n{DIV_THIN}")
    print(f"  {BOLD}{BWHITE}{title}{RESET}")
    print(f"{DIV_THIN}")


def header(canal: str, version: str, mode: str) -> None:
    """Header principal em box drawing."""
    line1 = f" baixar-canal  v{version} "
    line2 = f" Canal: {canal} "
    line3 = f" Modo:  {mode} "
    width = max(len(line1), len(line2), len(line3)) + 2
    bar   = "━" * width
    print()
    print(f"{BCYAN}┏{bar}┓{RESET}")
    print(f"{BCYAN}┃{RESET}{BOLD}{line1:<{width}}{RESET}{BCYAN}┃{RESET}")
    print(f"{BCYAN}┃{RESET}{DIM}{line2:<{width}}{RESET}{BCYAN}┃{RESET}")
    print(f"{BCYAN}┃{RESET}{DIM}{line3:<{width}}{RESET}{BCYAN}┃{RESET}")
    print(f"{BCYAN}┗{bar}┛{RESET}")
    print()


# Mantém cprint para uso legado interno (evita quebrar chamadas existentes)
def cprint(color: str, msg: str, end: str = "\n") -> None:
    print(f"{color}{msg}{RESET}", end=end, flush=True)


def countdown(seconds: int, message: str) -> None:
    """Contagem regressiva com barra visual inline."""
    bar_width = 20
    try:
        for remaining in range(seconds, -1, -1):
            filled  = int((seconds - remaining) / seconds * bar_width) if seconds else bar_width
            bar     = f"{GREEN}{'█' * filled}{DIM}{'░' * (bar_width - filled)}{RESET}"
            pct     = int((seconds - remaining) / seconds * 100) if seconds else 100
            sys.stdout.write(f"\r  {WAIT}  {message} [{bar}] {pct:>3}%  {DIM}{remaining}s{RESET}  ")
            sys.stdout.flush()
            if remaining > 0:
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
      - script_dir: diretório onde este .py está salvo
      - yt_dlp_cmd: comando base para invocar o yt-dlp (python do venv + -m yt_dlp)
    """
    script_dir = Path(__file__).parent.resolve()
    python_exec = script_dir / ".venv" / "bin" / "python3"

    if not python_exec.is_file() or not os.access(python_exec, os.X_OK):
        err(f"Ambiente virtual não encontrado em {python_exec}")
        info("Execute a instalação das dependências no diretório do script.")
        sys.exit(1)

    yt_dlp_cmd = [str(python_exec), "-m", "yt_dlp"]
    return script_dir, yt_dlp_cmd


# ─── Cookies ──────────────────────────────────────────────────────────────────

def configure_cookies(cwd: Path, script_dir: Path, refresh: bool) -> list[str]:
    """
    Retorna os argumentos de cookie para o yt-dlp.
    Se refresh=True, apaga o cookies.txt existente na cwd antes de continuar.
    """
    cookies_file = cwd / "cookies.txt"

    if refresh:
        warn("--refresh-cookies ativo. Apagando cache antigo...")
        cookies_file.unlink(missing_ok=True)

    if cookies_file.is_file():
        info(f"Cookies em cache: {cookies_file.name}")
        return ["--cookies", str(cookies_file)]

    # Fallback: busca no diretório do script
    script_cookies = script_dir / "cookies.txt"
    if script_cookies.is_file() and not refresh:
        info("Cookies do diretório do script.")
        return ["--cookies", str(script_cookies)]

    warn(f"Extraindo cookies do Chrome → {cookies_file.name}")
    return ["--cookies-from-browser", "chrome", "--cookies", str(cookies_file)]


# ─── Detecção de Idioma ───────────────────────────────────────────────────────

def detect_language(yt_dlp_cmd: list[str], cookie_args: list[str], url: str) -> str:
    """
    Detecta o idioma nativo do canal pelo primeiro vídeo.
    Retorna string de filtro para --sub-langs (ex: '^pt$').
    """
    info("Detectando idioma nativo do canal...")
    result = subprocess.run(
        yt_dlp_cmd + cookie_args + ["--print", "language", "--playlist-end", "1", url],
        capture_output=True, text=True
    )
    native_lang = result.stdout.strip()

    if native_lang:
        lang_filter = f"^{native_lang}$"
        ok(f"Idioma detectado automaticamente: {BOLD}{native_lang}{RESET}  {DIM}(filtro: {lang_filter}){RESET}")
        return lang_filter

    err("Não foi possível detectar o idioma nativo do canal.")
    info("Use --lang (ex: --lang pt) para especificar o idioma.")
    sys.exit(1)


# ─── Arquivo de Histórico ────────────────────────────────────────────────────

def load_archive(path: Path) -> set[str]:
    """
    Carrega o arquivo de histórico do yt-dlp em memória como um set de IDs.
    Retorna set vazio se o arquivo não existir.
    Complexidade de lookup: O(1) em vez de O(n) por leitura de arquivo.
    """
    if not path.is_file():
        return set()
    ids: set[str] = set()
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line.startswith("youtube "):
                ids.add(line[len("youtube "):])
    return ids


# ─── Listagem de IDs ──────────────────────────────────────────────────────────

def load_dates_from_json(cwd: Path) -> dict[str, str]:
    """
    Lê os arquivos .info.json na cwd e retorna um dicionário {video_id: upload_date}.
    Lê apenas os campos 'id' e 'upload_date' de cada arquivo.
    """
    dates: dict[str, str] = {}
    for fpath in glob.glob(str(cwd / "*.info.json")):
        try:
            with open(fpath) as f:
                data = json.load(f)
            vid_id = data.get("id")
            upload_date = data.get("upload_date")
            if vid_id and upload_date:
                dates[vid_id] = upload_date
        except Exception:
            pass
    return dates


def get_video_ids(
    yt_dlp_cmd: list[str],
    cookie_args: list[str],
    url: str,
    date_limit: str,
    cwd: Path,
) -> list[str]:
    """
    Retorna a lista de IDs de vídeos do canal ordenada por data de upload (mais novo primeiro).

    Usa --flat-playlist --dump-json para obter IDs e datas diretamente do YouTube.
    Se release_timestamp for null para um vídeo, tenta obter a data do .info.json local
    como fallback. Vídeos sem data alguma são colocados ao final na ordem retornada pelo YouTube.
    Se date_limit for fornecido, filtra somente vídeos com upload_date >= date_limit.
    """
    info("Buscando vídeos e datas de upload...")  # linha limpa antes do spinner

    cmd = yt_dlp_cmd + cookie_args + ["--flat-playlist", "--dump-json", url, "--ignore-errors"]

    # Fallback: datas já conhecidas via .info.json local
    local_dates = load_dates_from_json(cwd)

    # (upload_date_str | None, video_id)
    entries: list[tuple[str | None, str]] = []
    count = 0

    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            vid_id = data.get("id")
            if not vid_id:
                continue

            # 1º tenta o upload_date direto
            date_str = data.get("upload_date")  # YYYYMMDD ou None

            # 2º fallback: release_timestamp (Unix) → YYYYMMDD
            if not date_str:
                ts = data.get("release_timestamp") or data.get("timestamp")
                if ts:
                    try:
                        date_str = datetime.fromtimestamp(ts).strftime("%Y%m%d")
                    except (OSError, OverflowError, ValueError):
                        date_str = None

            # 3º fallback: .info.json local já baixado
            if not date_str:
                date_str = local_dates.get(vid_id)

            entries.append((date_str, vid_id))
            count += 1
            sys.stdout.write(f"\r  {WAIT}  {DIM}coletando...{RESET}  {BCYAN}{count}{RESET} vídeos  ")
            sys.stdout.flush()
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        raise
    finally:
        sys.stdout.write("\r" + " " * 60 + "\r")
        sys.stdout.flush()

    if not entries:
        return []

    # Separa os que têm data dos que não têm
    with_date    = [(d, i) for d, i in entries if d is not None]
    without_date = [i for d, i in entries if d is None]

    # Aplica filtro de data (quando -d foi passado)
    if date_limit:
        info(f"Aplicando filtro: a partir de {date_limit}")
        with_date = [(d, i) for d, i in with_date if d >= date_limit]

    # Ordena por data decrescente (mais novo primeiro)
    with_date.sort(key=lambda x: x[0], reverse=True)

    n_dated   = len(with_date)
    n_undated = len(without_date)
    ok(f"{BOLD}{n_dated + n_undated}{RESET}{GREEN} vídeos na fila  "
       f"{DIM}({n_dated} com data · {n_undated} sem data){RESET}")

    # Vídeos com data (ordenados) + sem data (ordem YouTube, geralmente mais novos)
    return [i for _, i in with_date] + without_date


# ─── Pós-processamento de Legendas ────────────────────────────────────────────

def cleanup_subtitles(cwd: Path, folder_name: str, vid_id: str) -> None:
    """
    Remove variações duplicadas de legenda geradas pelo yt-dlp,
    mantendo apenas o arquivo com o menor nome (ex: prefere 'pt' sobre 'pt-BR').
    Renomeia de '.pt.srt' para '-pt.srt'.
    """
    pattern = str(cwd / f"{folder_name}-{vid_id}*.srt")
    legenda_files = glob.glob(pattern)

    if not legenda_files:
        return

    if len(legenda_files) > 1:
        warn(f"{len(legenda_files)} variações de legenda detectadas — mantendo apenas uma.")
        best = min(legenda_files, key=len)
        for arq in legenda_files:
            if arq != best:
                os.unlink(arq)
        final_file = Path(best)
    else:
        final_file = Path(legenda_files[0])

    # Renomear: FOLDER-ID.lang.srt → FOLDER-ID-lang.srt
    base_prefix = f"{folder_name}-{vid_id}"
    suffix = final_file.name[len(base_prefix):]

    if suffix.startswith(".") and final_file.suffix == ".srt" and suffix.count(".") >= 2:
        new_suffix = "-" + suffix.lstrip(".")
        new_name = final_file.parent / f"{base_prefix}{new_suffix}"
        final_file.rename(new_name)
        final_file = new_name

    info(f"Legenda salva: {DIM}{final_file.name}{RESET}")


# ─── Download Individual ──────────────────────────────────────────────────────

def download_video(
    yt_dlp_cmd: list[str],
    cookie_args: list[str],
    archive_args: list[str],
    vid_id: str,
    lang_opt: str,
    folder_name: str,
    audio_only: bool,
) -> int:
    """
    Executa o yt-dlp para baixar legendas ou áudio de um único vídeo.
    Retorna o exit code.
    """
    output_tmpl = f"{folder_name}-%(id)s"
    if audio_only:
        output_tmpl += ".%(ext)s"

    cmd = (
        yt_dlp_cmd
        + ["--js-runtimes", f"node:{NODE_PATH}"]
        + ["--ignore-no-formats-error"]
        + ["--write-info-json"]
        + (["-f", "ba[ext=webm]"] if audio_only else ["--skip-download", "--write-auto-sub", "--convert-subs", "srt"])
        + cookie_args
        + archive_args
        + (["--sub-langs", lang_opt] if not audio_only else [])
        + ["-o", output_tmpl]
        + [f"https://www.youtube.com/watch?v={vid_id}"]
    )

    proc = subprocess.Popen(cmd)
    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        raise  # repropaga para o handler principal
    return proc.returncode


# ─── Argparse ─────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="baixar-canal.py",
        description=(
            "Baixa legendas de todos os vídeos de um canal do YouTube.\n"
            f"Versão: {VERSION}\n\n"
            "Padrão de nome dos arquivos: [NOME_DA_PASTA]-[ID_VIDEO]-[LANG].srt"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("canal", help="ID do canal ou URL completa (ex: @FilipeDeschamps)")
    parser.add_argument("-l", "--lang", default="", metavar="LANG",
                        help="Idioma das legendas (ex: pt, en). Padrão: idioma nativo do canal")
    parser.add_argument("-a", "--audio-only", action="store_true",
                        help="Baixa APENAS o áudio do vídeo (webm/opus), sem legendas")
    parser.add_argument("-d", "--date", default="", metavar="DATA",
                        help="Data limite (posterior a). Formato: YYYYMMDD (ex: 20260101)")
    parser.add_argument("-rc", "--refresh-cookies", action="store_true",
                        help="Força a extração de novos cookies do Chrome (apaga cookies.txt existente)")
    parser.add_argument("-f", "--fast", action="store_true",
                        help="Modo rápido: pula o tempo de espera entre downloads")
    parser.add_argument("-v", "--version", action="version", version=f"Versão: {VERSION}")
    return parser.parse_args()


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    args = parse_args()

    cwd = Path.cwd()
    folder_name = cwd.name
    script_dir, yt_dlp_cmd = setup_environment()

    # Normalizar URL
    canal = args.canal
    url = canal if canal.startswith("http") else f"https://www.youtube.com/{canal}"

    # Modo de operação para o header
    mode_label = "Áudio" if args.audio_only else f"Legendas ({args.lang or 'auto'})"
    if args.date:
        mode_label += f"  ·  a partir de {args.date}"
    if args.fast:
        mode_label += "  ·  rápido"
    header(canal, VERSION, mode_label)

    # Arquivos de histórico (sempre na pasta atual)
    arquivo_historico = cwd / "historico.txt"
    arquivo_info = cwd / "historico-info.txt"

    section("Configuração")
    info(f"Pasta    : {folder_name}")
    info(f"Canal    : {url}")
    info(f"Histórico: {arquivo_historico.name}")

    # Cookies
    section("Autenticação")
    cookie_args = configure_cookies(cwd, script_dir, args.refresh_cookies)

    # Idioma
    section("Idioma")
    lang_opt = args.lang if args.lang else detect_language(yt_dlp_cmd, cookie_args, url)
    if args.lang:
        ok(f"Idioma definido pelo usuário: {BOLD}{lang_opt}{RESET}")

    # Após a 1ª chamada ao yt-dlp (detect_language ou skip), o cookies.txt já foi criado.
    # Recarregar para evitar extrair cookies do Chrome em cada vídeo.
    if "--cookies-from-browser" in cookie_args:
        cookie_args = configure_cookies(cwd, script_dir, False)
        info("Cookies salvos em cache — reaproveitando para os downloads.")

    section("Listagem de Vídeos")
    video_ids = get_video_ids(yt_dlp_cmd, cookie_args, url, args.date, cwd)

    if not video_ids:
        err("Nenhum vídeo encontrado ou erro ao acessar o canal.")
        sys.exit(1)

    total = len(video_ids)

    # Pré-carrega os históricos como sets (O(1) lookup por iteração)
    historico_ids = load_archive(arquivo_historico)
    info_ids      = load_archive(arquivo_info)
    info(f"Histórico: {len(historico_ids)} em historico.txt · {len(info_ids)} em historico-info.txt")

    # Contadores de sessão
    n_skip = n_ok = n_err = 0

    section(f"Download  {DIM}(0/{total}){RESET}")

    # ─── Loop principal ────────────────────────────────────────────────────────
    for current, vid_id in enumerate(video_ids, start=1):
        prefix = f"  {BLUE}[{current:>{len(str(total))}}/{total}]{RESET}"

        # Verificação dupla de histórico (O(1) — busca em set, não em arquivo)
        in_historico = vid_id in historico_ids
        in_info      = vid_id in info_ids

        if in_historico and in_info:
            n_skip += 1
            print(f"{prefix} {SKIP} {DIM}{vid_id}{RESET}  {DIM}já processado{RESET}")
            continue

        # Arquivo travado: define se passa o archive ao yt-dlp
        archive_args = ["--download-archive", str(arquivo_historico)]

        if in_historico:
            info_json = cwd / f"{folder_name}-{vid_id}.info.json"
            if not info_json.is_file():
                print(f"{prefix} {WARN} {BYELLW}{vid_id}{RESET}  {DIM}no histórico, JSON ausente — baixando metadados{RESET}")
                archive_args = []
            else:
                n_skip += 1
                print(f"{prefix} {SKIP} {DIM}{vid_id}{RESET}  {DIM}já no histórico{RESET}")
                continue

        mode_str = "ÁUDIO" if args.audio_only else f"legenda/{lang_opt}"
        print(f"{prefix} {DL} {BCYAN}{vid_id}{RESET}  {DIM}{mode_str}{RESET}")

        exit_code = download_video(
            yt_dlp_cmd=yt_dlp_cmd,
            cookie_args=cookie_args,
            archive_args=archive_args,
            vid_id=vid_id,
            lang_opt=lang_opt,
            folder_name=folder_name,
            audio_only=args.audio_only,
        )

        if exit_code == 0:
            n_ok += 1
            # Atualiza os sets em memória para evitar re-download no mesmo run
            historico_ids.add(vid_id)
            info_ids.add(vid_id)

            if not args.audio_only:
                cleanup_subtitles(cwd, folder_name, vid_id)

            if not args.fast:
                sleep_val = random.randint(1, 5)
                countdown(sleep_val, "Aguardando")
            else:
                print(f"         {OK} {DIM}ok{RESET}")
        else:
            n_err += 1
            print(f"         {ERR} {BRED}falha (código {exit_code}) — possível bloqueio 429{RESET}")
            if not args.fast:
                countdown(300, "Resfriamento")
            info("Retomando...")

    # ─── Resumo final ──────────────────────────────────────────────────────────
    print(f"\n{DIV_THICK}")
    print(f"  {BOLD}{BWHITE}Sessão concluída{RESET}")
    print(f"{DIV_THICK}")
    print(f"  {OK}  Baixados  : {BGREEN}{n_ok}{RESET}")
    print(f"  {SKIP}  Pulados   : {DIM}{n_skip}{RESET}")
    if n_err:
        print(f"  {ERR}  Erros     : {BRED}{n_err}{RESET}")
    print(f"  {INFO}  Total fila : {total}")
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n  {WARN}  {BYELLW}Interrompido pelo usuário (Ctrl+C).{RESET}  {DIM}Saindo...{RESET}")
        sys.exit(130)  # Código 130 = SIGINT (padrão Unix)
