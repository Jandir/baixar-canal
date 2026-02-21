# Baixar Canal

Script **Python** para baixar legendas (automáticas ou manuais) de todos os vídeos de um canal do YouTube de forma sequencial e controlada.

> O script shell `baixar-canal.sh` foi substituído por `baixar-canal.py`. Use a versão Python para todos os novos downloads.

---

## Funcionalidades

- **Download em massa** — processa todo o canal a partir de um ID ou URL.
- **Ordenação por data** — busca IDs e datas de upload via `--flat-playlist --dump-json`; processa do mais novo para o mais antigo.
- **Histórico de downloads** — arquivo `historico.txt` gerado automaticamente; retomada sem duplicatas.
- **Detecção de idioma** — detecta o idioma nativo do canal automaticamente se não especificado.
- **Controle de rate limit** — aguarda 1–5 s entre downloads; em caso de erro (429), entra em resfriamento de 5 min.
- **Limpeza de legendas** — mantém apenas a variação mais simples (ex: `pt` em vez de `pt-BR`).
- **Cookies em cache** — extrai cookies do Chrome uma única vez por sessão e reutiliza `cookies.txt`.
- **Interrupção limpa** — Ctrl+C encerra o processo `yt-dlp` filho antes de sair.

---

## Pré-requisitos

| Dependência | Uso |
|---|---|
| **Python 3.10+** | Runtime principal |
| **yt-dlp** | Download de legendas/áudio (instalado no venv) |
| **Node.js** | JS runtime para o yt-dlp |
| **Chrome** | Extração de cookies de autenticação |

---

## Instalação

```bash
# 1. Criar o ambiente virtual e instalar o yt-dlp
cd baixar-canal
python3 -m venv .venv
.venv/bin/pip install yt-dlp

# 2. (Opcional) Criar alias no ~/.zshrc
echo 'alias baixar="python3 /caminho/para/baixar-canal.py"' >> ~/.zshrc
```

---

## Uso

```bash
python3 baixar-canal.py [OPÇÕES] <ID_DO_CANAL_OU_URL>
# ou, com o alias:
baixar [OPÇÕES] <ID_DO_CANAL_OU_URL>
```

### Exemplos

```bash
# Detectar idioma automaticamente
baixar @FilipeDeschamps

# Forçar idioma (evita chamada extra ao YouTube)
baixar -l pt @FilipeDeschamps

# Baixar somente vídeos publicados após a data
baixar -d 20250101 @FilipeDeschamps

# Modo somente áudio (webm/opus)
baixar -a @FilipeDeschamps

# Renovar cookies + modo rápido
baixar -rc -f @FilipeDeschamps
```

### Opções

| Opção | Descrição |
|---|---|
| `-l, --lang <LANG>` | Idioma das legendas (`pt`, `en`, …). Padrão: detectado automaticamente |
| `-a, --audio-only` | Baixa apenas o áudio (webm/opus), sem legendas |
| `-d, --date <YYYYMMDD>` | Filtra vídeos publicados **após** a data informada |
| `-rc, --refresh-cookies` | Força renovação dos cookies (apaga `cookies.txt` existente) |
| `-f, --fast` | Modo rápido: sem delay entre downloads |
| `-v, --version` | Exibe a versão |
| `-h, --help` | Exibe a ajuda |

---

## Arquivos gerados

| Arquivo | Descrição |
|---|---|
| `historico.txt` | IDs já processados (formato yt-dlp archive) |
| `cookies.txt` | Cookies do Chrome em cache (reutilizados na sessão) |
| `<pasta>-<id>-<lang>.srt` | Legenda do vídeo |
| `<pasta>-<id>.info.json` | Metadados do vídeo |

---

## Licença

MIT
