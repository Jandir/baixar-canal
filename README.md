# Baixar Canal

Script em Shell Bash para baixar legendas (legendas automáticas ou manuais) de **todos** os vídeos de um canal do YouTube de forma sequencial e controlada.

## Funcionalidades

- **Download em Massa**: Processa todo o canal dado um ID.
- **Controle de Rate Limit via Delay Inteligente**: Aguarda entre 1 e 30 segundos entre downloads bem-sucedidos para evitar bloqueios do YouTube (HTTP 429). Em caso de erro, aguarda 5 minutos (cool-down). Esse delay pode ser pulado com a opção `--fast`.
- **Histórico de Downloads**: Mantém um arquivo `historico.txt` para pular vídeos já processados, permitindo interromper e retomar o processo sem downloads duplicados e perda de tempo.
- **Detecção de Idioma**: Tenta detectar o idioma nativo do canal automaticamente se não for especificado.
- **Limpeza de Duplicatas**: Se houver múltiplas variações de legenda (ex: `pt` e `pt-BR`), mantém apenas a versão mais curta/simples.

## Pré-requisitos

- **[yt-dlp](https://github.com/yt-dlp/yt-dlp)**: Ferramenta principal de download.
- **Python 3**: Usado para gerar tempos de espera aleatórios.
- **Bash**: Shell padrão (testado em macOS/Linux).

## Instalação

1. Clone este repositório:
   ```bash
   git clone https://github.com/SEU_USUARIO/baixar-canal.git
   cd baixar-canal
   ```

2. Dê permissão de execução ao script:
   ```bash
   chmod +x baixar-canal.sh
   ```

## Uso

Execute o script passando o ID do canal ou a URL do canal:

```bash
./baixar-canal.sh [OPÇÕES] <ID_DO_CANAL>
```

### Exemplos

Baixar legendas do canal (detecta idioma automaticamente):
```bash
./baixar-canal.sh UCNzyuo5w8fTte9fRZLDqJUg
```

Forçar idioma português (`pt`):
```bash
./baixar-canal.sh --lang pt UCNzyuo5w8fTte9fRZLDqJUg
```

Baixar vídeos publicados após uma data específica:
```bash
./baixar-canal.sh --date 20240101 UCNzyuo5w8fTte9fRZLDqJUg
```

Modo somente áudio:
```bash
./baixar-canal.sh --audio-only UCNzyuo5w8fTte9fRZLDqJUg
```

### Opções

- `-l, --lang <LANG>`: Especifica o idioma das legendas (ex: `pt`, `en`). Padrão: detectado automaticamente.
- `-a, --audio-only`: Baixa apenas áudio (webm), sem legendas. Pensado para canais muito antigos que não têm legendas ou as legendas estejam com baixa qualidade.
- `-d, --date <DATA>`: Baixa vídeos publicados após a data (YYYYMMDD ou 'now-1week').
- `-rc, --refresh-cookies`: Força renovação de cookies.
- `-f, --fast`: Modo rápido (sem delay).
- `-v, --version`: Mostra a versão do script.
- `-h, --help`: Mostra a ajuda.

## Notas

- O script utiliza cookies do navegador Chrome (`--cookies-from-browser chrome`) para contornar algumas restrições. Certifique-se de ter o Chrome instalado ou ajuste o script conforme necessário.
- O arquivo `historico.txt` é gerado na pasta onde o script é executado.

## Licença

MIT
