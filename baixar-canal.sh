#!/bin/bash

#
# Script: baixar-canal.sh
# Descrição: Baixa legendas de todos os vídeos de um canal do YouTube.
#            O objetivo original é utilizar estas legendas como fontes no NotebookLM,
#            para alavancar estudos sobre determinado autor ou assunto.
#

VERSION="1.8.3"


# Cores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuração do ambiente Python local
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_EXEC="$SCRIPT_DIR/.venv/bin/python3"

# Verifica se o venv existe, senão alerta
if [ ! -x "$PYTHON_EXEC" ]; then
  echo -e "${RED}ERRO: Ambiente virtual não encontrado em $PYTHON_EXEC${NC}"
  echo "Por favor, execute a instalação das dependências no diretório do script."
  exit 1
fi

YT_DLP_CMD="$PYTHON_EXEC -m yt_dlp"

show_help() {
  echo -e "${BLUE}Uso:${NC} $0 [OPÇÕES] <ID_DO_CANAL>"
  echo ""
  echo -e "${BLUE}Descrição:${NC}"
  echo "  Baixa legendas de todos os vídeos de um canal do YouTube."
  echo "  Versão: $VERSION"
  echo ""
  echo -e "${BLUE}Opções:${NC}"
  echo "  -l, --lang <LANG>  Idioma das legendas (ex: pt, en). Padrão: idioma nativo do canal"
  echo "  -v, --version      Mostra a versão do script"
  echo "  -h, --help         Mostra esta mensagem de ajuda"
  echo ""
  echo -e "${BLUE}Exemplo:${NC}"
  echo "  $0 --lang pt UCNzyuo5w8fTte9fRZLDqJUg"
}

# Função de contagem regressiva
countdown() {
  local seconds=$1
  local message=$2
  
  while [ $seconds -gt 0 ]; do
    echo -ne "\r${message} ${seconds}s... \033[K"
    sleep 1
    : $((seconds--))
  done
  echo -ne "\r${message} 0s... \033[K\n"
}

LANG_OPT=""
ID_DO_CANAL=""

while [[ "$#" -gt 0 ]]; do
  case $1 in
    -h|--help) show_help; exit 0 ;;
    -v|--version) echo "Versão: $VERSION"; exit 0 ;;
    -l|--lang) LANG_OPT="$2"; shift ;;
    *) ID_DO_CANAL="$1" ;;
  esac
  shift
done

if [ -z "$ID_DO_CANAL" ]; then
  show_help
  exit 1
fi

echo -e "${CYAN}Iniciando script baixar-canal.sh - Versão: $VERSION${NC}"

# Verifica se o input já é uma URL completa
if [[ "$ID_DO_CANAL" =~ ^https?:// ]]; then
  URL_FINAL="$ID_DO_CANAL"
else
  URL_FINAL="https://www.youtube.com/$ID_DO_CANAL"
fi

# Define o caminho travado na pasta atual
ARQUIVO_TRAVADO="$(pwd)/historico.txt"

echo -e "${BLUE}Usando arquivo de histórico em:${NC} $ARQUIVO_TRAVADO"
echo -e "${BLUE}Processando canal:${NC} $URL_FINAL"

# Configuração de Cookies
COOKIES_FILE="cookies.txt"
if [ -f "$COOKIES_FILE" ]; then
  echo -e "${YELLOW}Usando cookies em cache: ${COOKIES_FILE}${NC}"
  COOKIE_ARGS="--cookies $COOKIES_FILE"
else
  echo -e "${YELLOW}Cookies em cache não encontrados. Extraindo do navegador e salvando em: ${COOKIES_FILE}${NC}"
  COOKIE_ARGS="--cookies-from-browser chrome --cookies $COOKIES_FILE"
fi

# Detecta a língua nativa do primeiro vídeo do canal
echo -e "${YELLOW}Detectando idioma nativo do canal...${NC}"
NATIVE_LANG=$($YT_DLP_CMD $COOKIE_ARGS --print "language" --playlist-end 1 "$URL_FINAL" 2>/dev/null)

if [ -z "$LANG_OPT" ]; then
  if [ -n "$NATIVE_LANG" ]; then
    # Usa strict match para evitar múltiplas variações e economizar requisições
    # Regex ^...$ garante que pegamos apenas o que foi detectado ou solicitado
    LANG_OPT="^${NATIVE_LANG}$"
    echo -e "${GREEN}Idioma não especificado. Usando idioma nativo detectado:${NC} $NATIVE_LANG (Filtro estrito: $LANG_OPT)"
  else
    echo -e "${RED}ERRO: Não foi possível detectar o idioma nativo do canal.${NC}"
    echo "Por favor, especifique o idioma desejado usando a opção --lang (ex: --lang pt)."
    echo "Isso evita o download desnecessário de todas as línguas disponíveis."
    exit 1
  fi
fi

# 1. Obter lista de IDs dos vídeos
echo -e "${YELLOW}Obtendo lista de vídeos do canal (isso pode demorar um pouco)...${NC}"
VIDEO_IDS=$($YT_DLP_CMD $COOKIE_ARGS --flat-playlist --print id "$URL_FINAL" --ignore-errors)

if [ -z "$VIDEO_IDS" ]; then
  echo -e "${RED}Nenhum vídeo encontrado ou erro ao acessar o canal.${NC}"
  exit 1
fi

TOTAL_VIDEOS=$(echo "$VIDEO_IDS" | wc -l | tr -d ' ')
CURRENT=0

echo -e "${CYAN}Total de vídeos encontrados:${NC} $TOTAL_VIDEOS"

# 2. Iterar sobre os vídeos
for VID_ID in $VIDEO_IDS; do
  CURRENT=$((CURRENT + 1))
  
  # Verifica se já está no histórico
  if [ -f "$ARQUIVO_TRAVADO" ] && grep -q "youtube $VID_ID" "$ARQUIVO_TRAVADO"; then
    echo -e "${BLUE}[$CURRENT/$TOTAL_VIDEOS]${NC} Vídeo $VID_ID já está no histórico. ${YELLOW}Pulando...${NC}"
    continue
  fi

  echo -e "${BLUE}[$CURRENT/$TOTAL_VIDEOS]${NC} Baixando legendas para: ${CYAN}$VID_ID${NC} ($LANG_OPT)"

  # Executa yt-dlp para um único vídeo
  $YT_DLP_CMD \
    --js-runtimes node:"/Users/jandirp/.nvm/versions/node/v22.16.0/bin/node" \
    --ignore-no-formats-error \
    --write-auto-sub \
    --convert-subs srt \
    --write-info-json \
    --skip-download \
    $COOKIE_ARGS \
    --download-archive "$ARQUIVO_TRAVADO" \
    --sub-langs "$LANG_OPT" \
    -o "%(id)s" \
    "https://www.youtube.com/watch?v=$VID_ID"

  EXIT_CODE=$?

  if [ $EXIT_CODE -eq 0 ]; then
    # Sucesso: Limpar legendas duplicadas se houver
    shopt -s nullglob
    LEGENDA_FILES=("${VID_ID}"*.srt)
    shopt -u nullglob

    if [ ${#LEGENDA_FILES[@]} -gt 1 ]; then
      echo -e "${YELLOW}Detectadas ${#LEGENDA_FILES[@]} variações de legenda. Mantendo apenas uma...${NC}"
      
      MELHOR_ARQ="${LEGENDA_FILES[0]}"
      
      for ARQ in "${LEGENDA_FILES[@]}"; do
        # Critério: menor nome de arquivo (preferência por "pt" sobre "pt-BR")
        if [ ${#ARQ} -lt ${#MELHOR_ARQ} ]; then
          MELHOR_ARQ="$ARQ"
        fi
      done
      
      for ARQ in "${LEGENDA_FILES[@]}"; do
        if [ "$ARQ" != "$MELHOR_ARQ" ]; then
          rm "$ARQ"
        fi
      done
      echo -e "${GREEN}Legenda mantida:${NC} $MELHOR_ARQ"
    fi

    # Sucesso: esperar tempo padrão estendido (30 a 60s)
    SLEEP_VAL=$(python3 -c 'import random; print(random.randint(1, 5))')
    countdown "$SLEEP_VAL" "${GREEN}Sucesso!${NC} Aguardando"
  else
    # Falha: possível 429 ou outro erro. Esperar 5 minutos.
    echo -e "${RED}AVISO: Falha no download (código $EXIT_CODE). Possível bloqueio temporário (429).${NC}"
    countdown 300 "${YELLOW}Entrando em modo de resfriamento. Aguardando${NC}"
    echo -e "${GREEN}Retomando...${NC}"
  fi
done

echo -e "${GREEN}Processamento concluído! (Versão: $VERSION)${NC}"