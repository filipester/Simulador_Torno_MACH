# Desenho do caminho da ferramenta com matplotlib (usado pela interface e
# para gerar imagens estáticas).

from mach_sim import Resultado

CORES = {"rapido": "#d62728", "corte": "#1f77b4", "arco": "#2ca02c"}


def desenhar(ax, res: Resultado, ate_linha=None, linha_atual=None, espelhar=True):
    """Desenha os segmentos até `ate_linha` (inclusive); destaca `linha_atual`.

    Vista: Z na horizontal, raio na vertical. Com `espelhar`, repete o caminho
    abaixo da linha de centro (em cinza) para dar a silhueta da peça.
    """
    ax.clear()
    ax.axhline(0, color="#888", lw=0.8, ls="-.")          # linha de centro
    ponta = None
    for s in res.segmentos:
        if ate_linha is not None and s.linha > ate_linha:
            break
        zs, rs = zip(*s.pontos)
        atual = s.linha == linha_atual
        ax.plot(zs, rs, color="#ff7f0e" if atual else CORES[s.tipo],
                ls="--" if s.tipo == "rapido" else "-",
                lw=2.6 if atual else (0.9 if s.tipo == "rapido" else 1.5))
        if espelhar and s.tipo != "rapido":
            ax.plot(zs, [-r for r in rs], color="#bbb", lw=1.0)
        ponta = s.pontos[-1]
    if ponta:
        ax.plot(*ponta, marker="o", color="#ff7f0e", ms=6, zorder=5)
    ax.set_aspect("equal", adjustable="datalim")
    ax.set_xlabel("Z (mm)")
    ax.set_ylabel("raio = X/2 (mm)")
    ax.grid(True, lw=0.3, alpha=0.6)
    return ponta
