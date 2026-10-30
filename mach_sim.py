# Simulação do caminho da ferramenta para programas MACH8/MACH9 de torno.
#
# Coordenadas de desenho: Z na horizontal, raio (X/2) na vertical — o perfil
# da peça visto de lado, acima da linha de centro.
#
# O que NÃO é simulado (vira aviso, não é desenhado):
#   - ciclos automáticos (G33, G37, G66, G67, G68, G74, G75, G76, G83);
#   - compensação de raio da ponta (G41/G42) — o caminho é o da ponta teórica;
#   - G73, subprogramas (P/L) e desvios (H).
# Não se tenta adivinhar a geometria desses blocos.

import math
from dataclasses import dataclass, field

from mach_parser import Bloco

CICLOS = {33: "rosca G33", 37: "ciclo de rosca G37", 66: "desbaste longitudinal G66",
          67: "desbaste transversal G67", 68: "desbaste paralelo ao perfil G68",
          74: "ciclo G74 (torneamento/furação)", 75: "ciclo G75 (canais/faceamento)",
          76: "ciclo de rosca G76", 83: "furação G83", 73: "G73 ponto a ponto"}

# G que só mudam estado (ou não afetam o desenho)
NEUTROS = {4, 7, 10, 11, 30, 40, 46, 47, 53, 54, 55, 58, 60, 61, 80, 94, 95, 96, 97}


@dataclass
class Segmento:
    linha: int
    tipo: str                     # "rapido", "corte" ou "arco"
    pontos: list[tuple[float, float]]   # (z, raio)


@dataclass
class Estado:
    z: float | None = None
    x: float | None = None        # sempre em diâmetro internamente
    modo: int = 0                 # 0 ou 1 (G2/G3 não são modais)
    diametro: bool = True         # G20 (padrão) / G21
    incremental: bool = False     # G90 / G91
    g92: bool = False             # origem definida por G92 (cancelada por G99)
    ferramenta: str = ""
    avanco: float | None = None
    rotacao: float | None = None

    @property
    def conhecida(self):
        return self.z is not None and self.x is not None


@dataclass
class Resultado:
    segmentos: list[Segmento] = field(default_factory=list)
    avisos: dict[int, list[str]] = field(default_factory=dict)   # linha -> avisos
    estados: dict[int, Estado] = field(default_factory=dict)     # linha -> estado após o bloco

    def avisar(self, linha, msg):
        self.avisos.setdefault(linha, []).append(msg)


def _arco(z0, r0, z1, r1, horario, raio=None, centro=None, passos_grau=3.0):
    """Pontos de um arco no plano (z, raio).

    `horario` é o sentido visto com Z para a direita e X para cima.
    Com `raio` (função R, até 180°) o centro é escolhido do lado que dá o
    arco menor, como o comando faz.
    """
    if centro is None:
        du, dv = z1 - z0, r1 - r0
        corda = math.hypot(du, dv)
        if corda == 0 or raio < corda / 2 - 1e-6:
            raise ValueError("G02/G03 - DEF.ILEGAL (raio menor que metade da corda)")
        h = math.sqrt(max(raio ** 2 - (corda / 2) ** 2, 0.0))
        nu, nv = (dv / corda, -du / corda) if horario else (-dv / corda, du / corda)
        cz, cr = (z0 + z1) / 2 + h * nu, (r0 + r1) / 2 + h * nv
    else:
        cz, cr = centro
        raio = math.hypot(z0 - cz, r0 - cr)
        if abs(math.hypot(z1 - cz, r1 - cr) - raio) > 0.01:
            raise ValueError("G02/G03 - DEF.ILEGAL (ponto final fora do círculo de I/K)")

    a0 = math.atan2(r0 - cr, z0 - cz)
    a1 = math.atan2(r1 - cr, z1 - cz)
    varredura = a1 - a0
    if horario and varredura > 0:
        varredura -= 2 * math.pi
    elif not horario and varredura < 0:
        varredura += 2 * math.pi
    n = max(2, int(abs(math.degrees(varredura)) / passos_grau) + 1)
    return [(cz + raio * math.cos(a0 + varredura * i / n),
             cr + raio * math.sin(a0 + varredura * i / n)) for i in range(n + 1)]


def simular(blocos: list[Bloco], torre_traseira: bool = True) -> Resultado:
    """Percorre os blocos e gera os segmentos do caminho da ferramenta.

    `torre_traseira`: no MACH, com torre traseira G2 é horário; com torre
    dianteira o sentido inverte (manual MACH9, item 10.3).
    """
    res = Resultado()
    st = Estado()

    for b in blocos:
        for a in b.avisos:
            res.avisar(b.linha, a)
        if not b.palavras:
            res.estados[b.linha] = Estado(**vars(st))
            continue

        gs = [0 if g is None else int(g) for g in b.valores("G")]
        movimento = None
        for g in gs:
            if g in (0, 1, 2, 3):
                movimento = g
            elif g == 20:
                st.diametro = True
            elif g == 21:
                # No MACH G21 = X em raio e vem sozinho no bloco. 'G21 G40 G90 G95'
                # é o cabeçalho ISO/Fanuc (G21 = milímetro): aí o X continua em diâmetro.
                if any(o in gs for o in (40, 54, 90, 94, 95)):
                    res.avisar(b.linha, "cabeçalho em estilo ISO: G21 lido como MILÍMETRO "
                                        "(no MACH seria X em raio); X continua em diâmetro")
                else:
                    st.diametro = False
            elif g == 90:
                st.incremental = False
            elif g == 91:
                st.incremental = True
            elif g == 99:
                st.g92 = False
            elif g == 70:
                res.avisar(b.linha, "G70 (polegada): valores desenhados como se fossem mm")
            elif g in CICLOS:
                res.avisar(b.linha, f"{CICLOS[g]}: ciclo não simulado, não desenhado")
            elif g == 41 or g == 42:
                res.avisar(b.linha, f"G{g}: compensação de raio não simulada (desenha a ponta teórica)")
            elif g not in NEUTROS and g != 92:
                res.avisar(b.linha, f"G{g}: função não reconhecida")

        if b.tem("T"):
            st.ferramenta = "T a definir" if b.nua("T") else f"T{int(b.valor('T')):04d}"
        if b.tem("F"):
            st.avanco = b.valor("F")
        if b.tem("S"):
            st.rotacao = b.valor("S")
        if b.tem("P") or b.tem("H"):
            res.avisar(b.linha, "subprograma/desvio (P/L/H) não simulado")

        if any(g in CICLOS for g in gs):
            res.estados[b.linha] = Estado(**vars(st))
            continue

        fator = 1.0 if st.diametro else 2.0   # X interno sempre em diâmetro
        alvo_x, alvo_z = st.x, st.z
        if b.tem("X"):
            v = b.valor("X") * fator
            alvo_x = (st.x or 0.0) + v if st.incremental else v
        if b.tem("Z"):
            v = b.valor("Z")
            alvo_z = (st.z or 0.0) + v if st.incremental else v
        if b.tem("U"):
            alvo_x = (st.x or 0.0) + b.valor("U") * fator
        if b.tem("W"):
            alvo_z = (st.z or 0.0) + b.valor("W")

        mexe_eixo = any(b.tem(e) for e in "XZUW")

        if 92 in gs:
            # G92 X Z: declara a posição atual da ferramenta (sem movimento).
            if b.tem("X") or b.tem("Z"):
                st.x, st.z, st.g92 = alvo_x, alvo_z, True
            res.estados[b.linha] = Estado(**vars(st))
            continue

        if not mexe_eixo:
            if movimento in (0, 1):
                st.modo = movimento
            res.estados[b.linha] = Estado(**vars(st))
            continue

        g = movimento if movimento is not None else st.modo

        # 'GXZ' (X e Z sem valor) fora de G92 = ida ao zero-máquina: a posição
        # em relação à peça fica desconhecida até o próximo G92.
        if b.nua("X") and b.nua("Z") and not st.g92:
            res.avisar(b.linha, "GXZ: ida ao zero-máquina (não desenhado; posição definida no próximo G92)")
            st.x = st.z = None
            st.modo = 0
            res.estados[b.linha] = Estado(**vars(st))
            continue

        if not st.conhecida:
            # Primeiro movimento sem posição de partida conhecida: só posiciona.
            if alvo_x is not None and alvo_z is not None:
                st.x, st.z = alvo_x, alvo_z
            else:
                st.x, st.z = alvo_x, alvo_z
                res.avisar(b.linha, "posição inicial incompleta (falta X ou Z antes deste bloco)")
            if g in (0, 1):
                st.modo = g
            res.estados[b.linha] = Estado(**vars(st))
            continue

        z0, r0 = st.z, st.x / 2
        z1, r1 = alvo_z, alvo_x / 2
        if g in (0, 1):
            if (z0, r0) != (z1, r1):
                res.segmentos.append(Segmento(b.linha, "rapido" if g == 0 else "corte", [(z0, r0), (z1, r1)]))
            if g == 1 and st.avanco is None:
                res.avisar(b.linha, "G1 sem avanço (F) definido")
            st.modo = g
        else:
            horario = (g == 2) == torre_traseira
            try:
                if b.tem("R"):
                    pts = _arco(z0, r0, z1, r1, horario, raio=b.valor("R"))
                elif b.tem("I") and b.tem("K"):
                    i = b.valor("I") * fator
                    pts = _arco(z0, r0, z1, r1, horario, centro=(b.valor("K"), i / 2))
                else:
                    raise ValueError("G2/G3 sem R nem I/K")
                res.segmentos.append(Segmento(b.linha, "arco", pts))
            except ValueError as e:
                res.avisar(b.linha, str(e))
            st.modo = 1   # G2/G3 não são modais e autorizam G1 nos blocos seguintes
        st.x, st.z = alvo_x, alvo_z
        res.estados[b.linha] = Estado(**vars(st))

    return res
