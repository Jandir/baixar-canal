# Escriba

Script **Python** de alta resiliência para baixar legendas (automáticas ou manuais) e metadados de todos os vídeos de um canal do YouTube de forma sequencial e controlada.
Caso um vídeo não possua legenda, o script pode fazer o download do **áudio de fallback** ou simplesmente registrá-lo para ser ignorado em buscas futuras, otimizando o tempo.

> O script original `baixar-canal` foi reescrito e rebatizado como **Escriba** (`escriba.py`). Esta nova versão utiliza um motor JSON assíncrono para mapeamento de estado, abandona o tráfego bloqueante de I/O em arquivos de texto antigos, e introduz auto-cura (auto-healing) para cookies corrompidos do Chrome.

---

## Funcionalidades Principais

- **Mapeamento JSON Assíncrono** — Na primeira execução, o script descobre todos os IDs do canal via `--flat-playlist` e usa um pool de threads múltiplas para extrair datas paralelamente, salvando o estado em um arquivo `lista_[canal].json`.
- **Download Deliberado em Massa** — Processa os canais apenas focando nos vídeos não baixados (cross-checking o JSON de tracking na memória).
- **Auto-cura de Autenticação (Cookies)** — Se o Chrome exportar diretivas de cookies inválidas ou corrompidas que crasham o `yt-dlp`, o Escriba deleta secretamente o cache quebrado e extrai novos cookies on-the-fly sem interromper o processo.
- **Detecção de Idioma Estrita** — Auto-detecta o idioma nativo de um canal. Lida inteligentemente com canais que usam `/videos` ou URLs puras para não falhar na extração global.
- **Injeção de JS Runtime** — Propaga globalmente caminhos de Node.js via `NODE_PATH` para quebrar as proteções baseadas em Javascript de listas do YouTube moderno.
- **Limpeza Profunda de Legendas** — Deduplica roll-ups do YouTube, remove formatação XML/HTML e limpa o texto (`--txt`) sem timestamps nativamente.
- **Fallback de Áudio (Opcional)** — Se configurado via flag, vídeos sem legenda disparam o download automático de seu respectivo áudio para a pasta de fallback `audios/`.

---

## Pré-requisitos

| Dependência | Descrição |
|---|---|
| **Python 3.10+** | Runtime de execução central |
| **yt-dlp** | Mecanismo subjacente de download de streams (instalado pelo venv) |
| **Node.js** | JS runtime obrigatório para desencriptar requisições do YouTube atual |
| **Chrome** | Extração passiva de autenticação base (necessário logado no YT) |

---

## Instalação e Ambiente

```bash
# 1. Entre no diretório e crie o ambiente virtual
cd escriba
python3 -m venv .venv
.venv/bin/pip install yt-dlp python-dotenv

# 2. (Opcional) Crie o alias no ~/.zshrc para rodar em qualquer pasta
echo 'alias escriba="/caminho/para/escriba/.venv/bin/python3 /caminho/para/escriba/escriba.py"' >> ~/.zshrc
source ~/.zshrc
```

---

## Uso

Vá para a pasta desejada (onde deseja armazenar as legendas/JSON) e invoque o script:

```bash
# Executando via interpretador explícito:
python3 /caminho/para/escriba/escriba.py [OPÇÕES] <ID_DO_CANAL_OU_URL>

# Ou, rodando através do alias configurado:
escriba [OPÇÕES] <ID_DO_CANAL_OU_URL>
```

### Exemplos de Uso

```bash
# Comportamento Padrão: mapear canal, descobrir língua, processar incrementalmente
escriba @FilipeDeschamps

# Forçar idioma (evita a fase de heurística no vídeo mais recente)
escriba -l pt @FilipeDeschamps

# Processar apenas o texto limpo sem timestamps do SRT (Gera um .txt legível)
escriba --txt @FilipeDeschamps

# Habilitar Fallback de Áudio: Vídeo sem legenda? Baixa o áudio dele em `audios/`
escriba --audio-fallback @FilipeDeschamps

# Baixar somente vídeos publicados estritamente APÓS a data informada
escriba -d 20260101 @FilipeDeschamps

# Forçar purga imediata do cache de Cookies + Modo Turbo (sem sleep entre requests)
escriba -rc -f @FilipeDeschamps
```

### Flags Referenciadas

| Opção | Ação |
|---|---|
| `-l, --lang` | Determina o idioma das legendas (`pt`, `en`, …). Padrão: Automático. |
| `-t, --txt` | Exporta a legenda extraída diretamente para um `.txt` limpo. O `.srt` é apagado. |
| `--keep-srt` | Se `--txt` for usado, essa flag preserva o original em `.srt` no disco também. |
| `--audio-fallback`| Ao invés de apenas marcar vídeos com erro 404 de legendas, baixa o Áudio (`ba`). |
| `-a, --audio-only`| Pula a aba de subs completamete e baixa *exclusivamente* o áudio bruto de cada item. |
| `-d, --date` | Filtra o dataset. Formato rigoroso: `YYYYMMDD` |
| `-rc, --refresh` | Força renovação destrutiva do arquivo `cookies.txt` base. |
| `-f, --fast` | Ignora o resfriamento de Anti-Spam padrão (delay de instantes entre requisições). |

---

## Estrutura de Arquivos de Rastreio (State Cache)

O Escriba mudou a arquitetura legada.

| Arquivo Tracker | Significado |
|---|---|
| `lista_[canal].json` | O Banco de Dados Atômico Primário. Ao invés do `historico.txt` velho que precisava de checagem I/O linear, o JSON mantém um cache vivo de: `video_id`, o booleano `subtitle_downloaded`, a `publish_date` original do video, e flag `has_no_subtitle` de +30 dias. |
| `historico.txt.bak` | Gerados pela função de **Auto-Migração**. Se rodar o ecosistema "Escriba" em uma pasta velha do projeto "Baixar Canal", o Escriba consolida o texto em JSON e renomeia os remanescentes textuais em segundos. |
| `<pasta>-<id>.info.json`| Metadata integral por ID de video extraída pelo `yt-dlp`. |

## Troubleshooting

- **Travamentos em Fase 1 ("Nenhum vídeo retornado")**: Em atualizações severas do Google contra raspadores, abra o seu terminal e execute: `/Users/jandirp/scripts/escriba/.venv/bin/python3 -m pip install -U yt-dlp` para puxar os patches open-source mais modernos da comunidade e reiniciar o seu ambiente invencível.

---

## Licença

MIT
