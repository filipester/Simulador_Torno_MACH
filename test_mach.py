# Testes do interpretador/simulador. Rodar com: python -m unittest -v

import math
import unittest

from mach_parser import ler_bloco, ler_texto
from mach_sim import simular


def avisos(res):
    return [a for v in res.avisos.values() for a in v]


class Leitura(unittest.TestCase):
    def test_numero_sem_zeros_e_espaco(self):
        b = ler_bloco("N040 G00 X 150. Z.2 F.25#", 0)
        self.assertEqual(b.sequencia, "040")
        self.assertEqual(b.palavras, [("G", 0.0), ("X", 150.0), ("Z", 0.2), ("F", 0.25)])
        self.assertEqual(b.avisos, [])

    def test_g_e_eixos_sem_valor(self):
        b = ler_bloco("N003 GXZ", 0)
        self.assertEqual(b.palavras, [("G", None), ("X", None), ("Z", None)])
        self.assertEqual(b.valor("X"), 0.0)
        self.assertTrue(b.nua("Z"))

    def test_comentarios(self):
        b = ler_bloco("N30 T0101;DESBASTE EXT.#", 0)
        self.assertEqual(b.palavras, [("T", 101.0)])
        self.assertEqual(b.comentario, "DESBASTE EXT.")
        b = ler_bloco("N030 G54 (verificar na máquina)", 0)
        self.assertEqual(b.palavras, [("G", 54.0)])

    def test_placeholder_de_ferramenta(self):
        b = ler_bloco("N002 T0?0? M6", 0)
        self.assertEqual(b.palavras, [("T", None), ("M", 6.0)])
        self.assertIn("ferramenta a definir (T0?0?)", b.avisos)

    def test_erros_de_digitacao_viram_aviso(self):
        self.assertTrue(any("G0.2" in a for a in ler_bloco("013 G1 Z0. G0.20", 0).avisos))
        self.assertTrue(any("'0'" in a for a in ler_bloco("014 G1 X19. 0 Z-1.5", 0).avisos))
        self.assertTrue(any("vírgula" in a for a in ler_bloco("G1 X23,80 Z-64.", 0).avisos))


class Simulacao(unittest.TestCase):
    def test_g92_define_origem_e_desenha_corte(self):
        r = simular(ler_texto("G99\nGXZ\nG92 X150. Z10.\nG0 X26. Z2.\nG1 Z-60. F.2"))
        self.assertEqual([s.tipo for s in r.segmentos], ["rapido", "corte"])
        self.assertEqual(r.segmentos[0].pontos, [(10.0, 75.0), (2.0, 13.0)])   # raio = X/2
        self.assertEqual(r.segmentos[1].pontos[-1], (-60.0, 13.0))

    def test_gxz_nao_e_desenhado(self):
        r = simular(ler_texto("G0 X50. Z5.\nGXZ\nG0 X20. Z1."))
        self.assertEqual(r.segmentos, [])           # partida desconhecida após GXZ
        self.assertTrue(any("zero-máquina" in a for a in avisos(r)))

    def test_arco_r_torre_traseira_g2_horario(self):
        # Fundo de canal: G2 R1 deve ser côncavo (centro acima do caminho).
        r = simular(ler_texto("G0 X37.1 Z-22.7\nG2 X35.6 Z-23.5 R1"))
        pts = r.segmentos[0].pontos
        (z0, r0), (z1, r1) = (-22.7, 18.55), (-23.5, 17.8)
        corda = math.hypot(z1 - z0, r1 - r0)
        h = math.sqrt(1 - (corda / 2) ** 2)
        nz, nr = -(r1 - r0) / corda, (z1 - z0) / corda          # normal com componente de raio > 0
        if nr < 0:
            nz, nr = -nz, -nr
        centro = ((z0 + z1) / 2 + h * nz, (r0 + r1) / 2 + h * nr)  # centro ACIMA = côncavo
        for z, rr in pts:
            self.assertAlmostEqual(math.hypot(z - centro[0], rr - centro[1]), 1.0, places=6)
        self.assertLess(pts[len(pts) // 2][1], (r0 + r1) / 2)     # arco passa abaixo da corda

    def test_torre_dianteira_inverte_sentido(self):
        prog = "G0 X37.1 Z-22.7\nG2 X35.6 Z-23.5 R1"
        tras = simular(ler_texto(prog)).segmentos[0].pontos
        diant = simular(ler_texto(prog), torre_traseira=False).segmentos[0].pontos
        self.assertLess(tras[len(tras) // 2][1], diant[len(diant) // 2][1])

    def test_arco_ik_absoluto_igual_ao_r(self):
        # Exemplo do manual MACH9: N70 G2 X44. Z40. R10. == G2 X44. Z40. I44. K50.
        base = "G0 X24. Z50.\n"
        com_r = simular(ler_texto(base + "G2 X44. Z40. R10.")).segmentos[0].pontos
        com_ik = simular(ler_texto(base + "G2 X44. Z40. I44. K50.")).segmentos[0].pontos
        self.assertEqual(len(com_r), len(com_ik))
        for a, b in zip(com_r, com_ik):
            self.assertAlmostEqual(a[0], b[0], places=6)
            self.assertAlmostEqual(a[1], b[1], places=6)

    def test_raio_impossivel(self):
        r = simular(ler_texto("G0 X20. Z0.\nG2 X40. Z-20. R1."))
        self.assertTrue(any("DEF.ILEGAL" in a for a in avisos(r)))

    def test_g21_programacao_em_raio(self):
        r = simular(ler_texto("G21\nG0 X10. Z0.\nG1 X12. F.1"))
        self.assertEqual(r.segmentos[0].pontos[-1], (0.0, 12.0))

    def test_g21_em_cabecalho_iso_e_milimetro(self):
        # 'G21 G40 G90 G95' é cabeçalho ISO: X segue em diâmetro e os arcos fecham.
        r = simular(ler_texto("G21 G40 G90 G95\nG0 X40. Z-22.\nG3 X37.2 Z-23.5 R1.5"))
        self.assertEqual([s.tipo for s in r.segmentos], ["arco"])
        self.assertEqual(r.segmentos[0].pontos[0], (-22.0, 20.0))
        self.assertTrue(any("estilo ISO" in a for a in avisos(r)))

    def test_incremental_u_w(self):
        r = simular(ler_texto("G0 X20. Z0.\nG1 U4. W-10. F.1"))
        self.assertEqual(r.segmentos[0].pontos[-1], (-10.0, 12.0))

    def test_ciclo_vira_aviso(self):
        r = simular(ler_texto("G0 X30. Z1.\nG74 X29. Z-131.2 I2. U1"))
        self.assertEqual(r.segmentos, [])
        self.assertTrue(any("não simulado" in a for a in avisos(r)))


if __name__ == "__main__":
    unittest.main()
