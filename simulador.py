# Simulador de torno para programas MACH8/MACH9 — interface (tkinter + matplotlib).
#
# Uso: python simulador.py [arquivo.nc|.txt|.docx]
# Teclas: ↓/→ próxima linha, ↑/← anterior, Home/End início/fim.

import os
import sys
import tkinter as tk
from tkinter import filedialog, ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure

from desenho import desenhar
from mach_parser import ler_arquivo
from mach_sim import simular

TIPOS = [("Programas CNC", "*.nc *.NC *.txt *.TXT *.docx"), ("Todos", "*.*")]


class Simulador(tk.Tk):
    def __init__(self, caminho=None):
        super().__init__()
        self.title("Simulador de Torno MACH")
        self.geometry("1280x760")
        self.blocos, self.res, self.caminho = [], None, None
        self.atual = -1
        self._limites = None
        self.torre_dianteira = tk.BooleanVar(value=False)
        self.espelhar = tk.BooleanVar(value=True)
        self._montar()
        if caminho:
            self.abrir(caminho)

    # ---- layout ---------------------------------------------------------
    def _montar(self):
        barra = ttk.Frame(self, padding=4)
        barra.pack(side=tk.TOP, fill=tk.X)
        ttk.Button(barra, text="Abrir…", command=self._escolher).pack(side=tk.LEFT)
        ttk.Button(barra, text="Recarregar", command=self._recarregar).pack(side=tk.LEFT, padx=(4, 12))
        for txt, cmd in (("⏮", lambda: self.ir(0)), ("◀", lambda: self.ir(self.atual - 1)),
                         ("▶", lambda: self.ir(self.atual + 1)), ("⏭", lambda: self.ir(len(self.blocos) - 1))):
            ttk.Button(barra, text=txt, width=3, command=cmd).pack(side=tk.LEFT)
        ttk.Checkbutton(barra, text="Torre dianteira", variable=self.torre_dianteira,
                        command=self._recalcular).pack(side=tk.LEFT, padx=(16, 4))
        ttk.Checkbutton(barra, text="Espelhar perfil", variable=self.espelhar,
                        command=self._redesenhar).pack(side=tk.LEFT)
        self.lbl_arquivo = ttk.Label(barra, text="(nenhum arquivo)", foreground="#555")
        self.lbl_arquivo.pack(side=tk.LEFT, padx=16)

        corpo = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        corpo.pack(fill=tk.BOTH, expand=True)

        esquerda = ttk.Frame(corpo)
        self.lista = tk.Listbox(esquerda, font=("Consolas", 11), activestyle="none",
                                selectbackground="#ff7f0e", exportselection=False, width=42)
        rolagem = ttk.Scrollbar(esquerda, command=self.lista.yview)
        self.lista.config(yscrollcommand=rolagem.set)
        rolagem.pack(side=tk.RIGHT, fill=tk.Y)
        self.lista.pack(fill=tk.BOTH, expand=True)
        self.lista.bind("<<ListboxSelect>>", lambda e: self._clicou_lista())
        corpo.add(esquerda, weight=1)

        direita = ttk.Frame(corpo)
        self.fig = Figure(figsize=(8, 5), layout="tight")
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.fig, master=direita)
        NavigationToolbar2Tk(self.canvas, direita).update()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.status = ttk.Label(direita, font=("Consolas", 11), padding=4)
        self.status.pack(fill=tk.X)
        self.txt_avisos = tk.Text(direita, height=6, font=("Segoe UI", 9), wrap=tk.WORD,
                                  background="#fff8e6")
        self.txt_avisos.pack(fill=tk.X)
        corpo.add(direita, weight=3)

        for tecla, passo in (("<Down>", 1), ("<Right>", 1), ("<Up>", -1), ("<Left>", -1)):
            self.bind(tecla, lambda e, p=passo: self._tecla(p))
        self.bind("<Home>", lambda e: self.ir(0))
        self.bind("<End>", lambda e: self.ir(len(self.blocos) - 1))

    # ---- arquivo --------------------------------------------------------
    def _escolher(self):
        inicial = os.path.dirname(self.caminho) if self.caminho else None
        c = filedialog.askopenfilename(filetypes=TIPOS, initialdir=inicial)
        if c:
            self.abrir(c)

    def _recarregar(self):
        if self.caminho:
            self.abrir(self.caminho, manter_linha=True)

    def abrir(self, caminho, manter_linha=False):
        self.caminho = caminho
        self.blocos = ler_arquivo(caminho)
        self.lbl_arquivo.config(text=os.path.basename(caminho))
        self.title(f"Simulador de Torno MACH — {os.path.basename(caminho)}")
        self.lista.delete(0, tk.END)
        for b in self.blocos:
            self.lista.insert(tk.END, b.texto.rstrip())
        self._recalcular(enquadrar=not manter_linha)
        self.ir(self.atual if manter_linha and self.atual >= 0 else len(self.blocos) - 1)

    # ---- simulação ------------------------------------------------------
    def _recalcular(self, enquadrar=True):
        self.res = simular(self.blocos, torre_traseira=not self.torre_dianteira.get())
        for i in range(len(self.blocos)):
            self.lista.itemconfig(i, background="#ffe8b0" if i in self.res.avisos else "")
        if enquadrar:
            self._limites = None
        self._redesenhar()

    def ir(self, linha):
        if not self.blocos:
            return
        self.atual = max(0, min(linha, len(self.blocos) - 1))
        self.lista.selection_clear(0, tk.END)
        self.lista.selection_set(self.atual)
        self.lista.see(self.atual)
        self._redesenhar()

    def _tecla(self, passo):
        self.ir(self.atual + passo)
        return "break"   # impede a Listbox de mover a seleção de novo

    def _clicou_lista(self):
        sel = self.lista.curselection()
        if sel and sel[0] != self.atual:
            self.ir(sel[0])

    def _redesenhar(self):
        if not self.res:
            return
        # Mantém o zoom do usuário entre passos; enquadra o programa todo ao abrir.
        limites = self._enquadramento() if self._limites is None else (self.ax.get_xlim(), self.ax.get_ylim())
        self._limites = limites
        desenhar(self.ax, self.res, ate_linha=self.atual, linha_atual=self.atual,
                 espelhar=self.espelhar.get())
        self.ax.set_xlim(*limites[0])
        self.ax.set_ylim(*limites[1])
        self.canvas.draw_idle()
        self._atualizar_status()

    def _enquadramento(self):
        # Enquadra pelo corte; rápidos até o ponto de troca (ex.: X150 Z10) ficam
        # parcialmente fora, senão a peça vira um risco no canto da tela.
        cortes = [s for s in self.res.segmentos if s.tipo != "rapido"] or self.res.segmentos
        pts = [p for s in cortes for p in s.pontos]
        if not pts:
            return (-10, 10), (-10, 10)
        zs = [z for z, _ in pts]
        rs = [r for _, r in pts] + ([-r for _, r in pts] if self.espelhar.get() else [0])
        mz = (max(zs) - min(zs)) * 0.05 + 1
        mr = (max(rs) - min(rs)) * 0.05 + 1
        return (min(zs) - mz, max(zs) + mz), (min(rs) - mr, max(rs) + mr)

    def _atualizar_status(self):
        st = self.res.estados.get(self.atual)
        if st and st.conhecida:
            pos = f"X{st.x:9.3f}  Z{st.z:9.3f}"
        else:
            pos = "X    ---    Z    ---  "
        f = f"{st.avanco:g}" if st and st.avanco is not None else "-"
        s = f"{st.rotacao:g}" if st and st.rotacao is not None else "-"
        t = st.ferramenta if st and st.ferramenta else "-"
        self.status.config(text=f"Linha {self.atual + 1}/{len(self.blocos)}   {pos}   "
                                f"{t}   F{f}   S{s}")

        self.txt_avisos.delete("1.0", tk.END)
        aqui = self.res.avisos.get(self.atual, [])
        for a in aqui:
            self.txt_avisos.insert(tk.END, f"► Linha {self.atual + 1}: {a}\n")
        total = sum(len(v) for v in self.res.avisos.values())
        if total:
            outras = sorted(l + 1 for l in self.res.avisos if l != self.atual)
            if outras:
                self.txt_avisos.insert(tk.END, f"Outras linhas com aviso: {', '.join(map(str, outras))}\n")
        else:
            self.txt_avisos.insert(tk.END, "Nenhum aviso no programa.")


if __name__ == "__main__":
    Simulador(sys.argv[1] if len(sys.argv) > 1 else None).mainloop()
