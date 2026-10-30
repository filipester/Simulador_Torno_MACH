# Leitura de programas CNC no dialeto MACH8/MACH9 (tornos Romi/MCS).
#
# Regras do dialeto que diferem do ISO "genérico" (manual R69001C - MACH9):
#   - '#' marca fim de bloco; ';' inicia comentário até o fim do bloco.
#   - 'G' sem número equivale a G0 (ex.: "GX35." = G0 X35.).
#   - Eixo sem valor vale zero (ex.: "GXZ" = G0 X0 Z0; "Z#" = Z0).
#   - Números podem omitir zeros: "Z.2", "X43.", "F.25".

import re
import zipfile
from dataclasses import dataclass, field

# Letra + número opcional (sinal, inteiro e/ou decimal). Número vazio = palavra "nua".
# Aceita espaço entre letra e número ("X 150.", como o CIMCO grava).
_TOKEN = re.compile(r"([A-Z])\s*([+-]?(?:\d+\.?\d*|\.\d+)?)")
# Número de sequência só conta se vier seguido de código (evita datas '20/08/2020').
_SEQUENCIA = re.compile(r"^\s*N?(\d+)(?=\s|;|#|[A-Za-z]|$)\s*")


@dataclass
class Bloco:
    linha: int                      # índice da linha no arquivo (0-based)
    texto: str                      # texto original da linha
    sequencia: str | None = None    # número N do bloco, se houver
    palavras: list[tuple[str, float | None]] = field(default_factory=list)
    comentario: str = ""
    avisos: list[str] = field(default_factory=list)

    def valores(self, letra):
        return [v for l, v in self.palavras if l == letra]

    def tem(self, letra):
        return any(l == letra for l, _ in self.palavras)

    def valor(self, letra):
        """Último valor da letra no bloco; palavra nua (sem número) vale 0."""
        vs = self.valores(letra)
        if not vs:
            return None
        return 0.0 if vs[-1] is None else vs[-1]

    def nua(self, letra):
        """True se a letra aparece sem valor (ex.: o X de 'GXZ')."""
        vs = self.valores(letra)
        return bool(vs) and vs[-1] is None


def ler_bloco(texto: str, linha: int) -> Bloco:
    b = Bloco(linha=linha, texto=texto)
    s = texto.strip()
    if not s:
        return b

    m = _SEQUENCIA.match(s)
    if m:
        b.sequencia = m.group(1)
        s = s[m.end():]

    s = s.split("#", 1)[0]
    if ";" in s:
        s, b.comentario = s.split(";", 1)
        b.comentario = b.comentario.strip()
    # Comentário entre parênteses é estilo ISO/Fanuc; aceito para não poluir avisos.
    parenteses = re.findall(r"\(([^)]*)\)", s)
    if parenteses:
        s = re.sub(r"\([^)]*\)", " ", s)
        b.comentario = " ".join([b.comentario, *parenteses]).strip()

    corpo = s.upper()
    # 'T0?0?': placeholder para ferramenta ainda não definida na torre
    placeholder = re.search(r"T([0-9?]{2,4})(?![0-9?])", corpo)
    if placeholder and "?" in placeholder.group(1):
        b.avisos.append(f"ferramenta a definir ({placeholder.group(0)})")
        corpo = corpo[:placeholder.start()] + "T" + corpo[placeholder.end():]
    if "," in corpo:
        b.avisos.append("vírgula como separador decimal (o comando não aceita); lido como ponto")
        corpo = corpo.replace(",", ".")

    pos = 0
    for t in _TOKEN.finditer(corpo):
        sobra = corpo[pos:t.start()].strip()
        if sobra:
            b.avisos.append(f"texto não reconhecido: '{sobra}'")
        letra, num = t.group(1), t.group(2)
        b.palavras.append((letra, float(num) if num not in ("", "+", "-") else None))
        pos = t.end()
    sobra = corpo[pos:].strip()
    if sobra:
        b.avisos.append(f"texto não reconhecido: '{sobra}'")

    for g in b.valores("G"):
        if g is not None and g != int(g):
            b.avisos.append(f"função G{g:g} inválida (G não tem casa decimal; seria F?)")
    return b


def ler_texto(texto: str) -> list[Bloco]:
    return [ler_bloco(l, i) for i, l in enumerate(texto.splitlines())]


def ler_arquivo(caminho: str) -> list[Bloco]:
    """Lê .nc/.txt (latin-1 tolerante) ou .docx (texto dos parágrafos)."""
    if caminho.lower().endswith(".docx"):
        return ler_texto(texto_do_docx(caminho))
    with open(caminho, "rb") as f:
        bruto = f.read()
    try:
        texto = bruto.decode("utf-8")
    except UnicodeDecodeError:
        texto = bruto.decode("cp1252", errors="replace")
    return ler_texto(texto)


def texto_do_docx(caminho: str) -> str:
    """Extrai os parágrafos de um .docx só com a stdlib.

    Linhas que não parecem código (ex.: o título 'Programa – M24 X 145 MM –
    03/06/2025') viram comentário, para não gerar avisos de texto não
    reconhecido. Código = começa com número de sequência ou com uma função
    seguida de número/eixo ('G1 X..', 'T0101', 'GXZ', 'S2000 M03').
    """
    xml = zipfile.ZipFile(caminho).read("word/document.xml").decode("utf-8")
    linhas = []
    for p in re.findall(r"<w:p[ >].*?</w:p>", xml, re.S):
        t = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", p))
        t = (t.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
              .replace("&quot;", '"').replace("&apos;", "'"))
        if not t.strip():
            continue
        codigo = _SEQUENCIA.match(t) or t.lstrip().startswith(";") or _PARECE_CODIGO.match(t)
        linhas.append(t if codigo else ";" + t)
    return "\n".join(linhas)


_PARECE_CODIGO = re.compile(r"^\s*(?:[GMTSFXZUWH]\s*[+-]?[\d.]|G\s*[XZ]|[XZ]\s*#?\s*$)")
