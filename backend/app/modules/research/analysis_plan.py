"""
analysis_plan.py — Núcleo de referência do PLANO DE ANÁLISE do piloto.
=====================================================================
Implementa (1) o índice de cegamento de Bang (validado) e (2) funções do plano
de análise: taxas com IC95% (viabilidade), e seleção de teste guiada por
normalidade (mudança intra-braço e comparação entre braços), com α = 5%.

Enquadramento: piloto de VIABILIDADE. Desfechos primários = viabilidade, adesão,
usabilidade e segurança (descritivos). Ansiedade e sono são EXPLORATÓRIOS
(gerador de hipóteses), sem poder para eficácia. Nada aqui demonstra efeito
clínico. Ferramenta complementar; não substitui cuidado profissional.

Nota de rigor sobre o índice de James: sua forma exata é um estatístico do tipo
kappa (JAMES et al., 1996) cuja normalização é sutil; para não arriscar uma
fórmula incorreta, aqui implementa-se o índice de BANG (2004), direcional e
validado, e recomenda-se calcular o índice de James com implementação validada
(ex.: pacote R 'BI') na análise final.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from scipy import stats

ALPHA = 0.05


# ----------------------------------------------------- Índice de Bang (cegamento)
def bang_blinding_index(n_correct: int, n_incorrect: int, n_dont_know: int) -> dict:
    """Índice de cegamento de Bang para UM braço.

    BI = (2*n_correct + n_dont_know)/N - 1, com N = total do braço.
    Intervalo [-1, 1]: 0 ≈ cegamento mantido; >0 tende a adivinhação correta
    (desblindagem no sentido correto); <0 tende a adivinhação oposta.
    """
    n = n_correct + n_incorrect + n_dont_know
    if n == 0:
        raise ValueError("Braço sem respondentes.")
    bi = (2 * n_correct + n_dont_know) / n - 1
    # IC95% por bootstrap (ilustrativo)
    labels = np.array([1] * n_correct + [-1] * n_incorrect + [0] * n_dont_know)
    rng = np.random.default_rng(42)
    boot = []
    for _ in range(2000):
        s = rng.choice(labels, size=n, replace=True)
        boot.append((2 * np.sum(s == 1) + np.sum(s == 0)) / n - 1)
    lo, hi = np.percentile(boot, [2.5, 97.5])
    return {"bang_bi": round(bi, 3), "ci95": (round(lo, 3), round(hi, 3)), "n": n,
            "interpretation": ("cegamento aparentemente mantido" if abs(bi) < 0.2
                               else "possível desblindagem — interpretar com cautela")}


# ----------------------------------------------------- Taxas de viabilidade (IC95% Wilson)
def rate_with_ci(k: int, n: int, z: float = 1.96) -> dict:
    """Proporção com IC95% de Wilson (recrutamento, adesão, retenção, etc.)."""
    if n == 0:
        return {"rate": None, "ci95": (None, None), "k": 0, "n": 0}
    p = k / n
    denom = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denom
    half = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return {"rate_pct": round(100 * p, 1), "ci95_pct": (round(100 * (center - half), 1),
            round(100 * (center + half), 1)), "k": k, "n": n}


# ----------------------------------------------------- Descritivos
def describe(x: list[float]) -> dict:
    a = np.asarray(x, float)
    return {"n": int(a.size), "mean": round(float(a.mean()), 2), "sd": round(float(a.std(ddof=1)), 2),
            "median": round(float(np.median(a)), 2),
            "iqr": (round(float(np.percentile(a, 25)), 2), round(float(np.percentile(a, 75)), 2))}


# ----------------------------------------------------- Seleção de teste (normalidade)
def within_arm_change(pre: list[float], post: list[float]) -> dict:
    """Mudança intra-braço: Shapiro nas diferenças → t pareado ou Wilcoxon."""
    pre, post = np.asarray(pre, float), np.asarray(post, float)
    diff = post - pre
    normal = stats.shapiro(diff).pvalue > ALPHA if diff.size >= 3 else False
    if normal:
        st = stats.ttest_rel(post, pre); test = "t pareado"
    else:
        st = stats.wilcoxon(post, pre); test = "Wilcoxon (pareado)"
    return {"test": test, "normal_diffs": bool(normal), "p_value": round(float(st.pvalue), 4),
            "mean_change": round(float(diff.mean()), 2)}


def between_arms(a: list[float], b: list[float]) -> dict:
    """Comparação entre braços: normalidade + variância → t (Welch) ou Mann-Whitney."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    na = stats.shapiro(a).pvalue > ALPHA if a.size >= 3 else False
    nb = stats.shapiro(b).pvalue > ALPHA if b.size >= 3 else False
    if na and nb:
        st = stats.ttest_ind(a, b, equal_var=False); test = "t de Welch"
    else:
        st = stats.mannwhitneyu(a, b, alternative="two-sided"); test = "Mann-Whitney U"
    return {"test": test, "both_normal": bool(na and nb), "p_value": round(float(st.pvalue), 4)}


def categorical(table: list[list[int]]) -> dict:
    """Qui-quadrado; se alguma esperada < 5, usar Fisher (2x2)."""
    arr = np.array(table)
    chi2, p, dof, exp = stats.chi2_contingency(arr)
    if (exp < 5).any() and arr.shape == (2, 2):
        _, p = stats.fisher_exact(arr); test = "Fisher exato"
    else:
        test = "Qui-quadrado"
    return {"test": test, "p_value": round(float(p), 4)}


# ----------------------------------------------------------------- Testes (auto-validação)
if __name__ == "__main__":
    ok = True
    def expect(name, got, want):
        global ok; good = got == want; ok &= good
        print(f"   {'✓' if good else '✗'} {name:46s} obtido={got}  esperado={want}")

    print("=" * 72); print("VALIDAÇÃO DO PLANO DE ANÁLISE"); print("=" * 72)

    print("\nÍndice de Bang (âncoras)")
    expect("todos corretos → +1", bang_blinding_index(20, 0, 0)["bang_bi"], 1.0)
    expect("todos incorretos → -1", bang_blinding_index(0, 20, 0)["bang_bi"], -1.0)
    expect("todos 'não sei' → 0", bang_blinding_index(0, 0, 20)["bang_bi"], 0.0)
    expect("metade/metade → 0", bang_blinding_index(10, 10, 0)["bang_bi"], 0.0)
    ex = bang_blinding_index(12, 6, 2)
    print(f"      exemplo (12/6/2): BI={ex['bang_bi']} IC95%={ex['ci95']} — {ex['interpretation']}")

    print("\nTaxas de viabilidade (IC95% Wilson)")
    r = rate_with_ci(14, 20)
    print(f"      adesão 14/20: {r['rate_pct']}%  IC95% {r['ci95_pct']}")
    expect("14/20 = 70,0%", r["rate_pct"], 70.0)

    print("\nSeleção de teste (dados SINTÉTICOS — apenas ilustrativo)")
    rng = np.random.default_rng(7)
    pre = rng.normal(12, 2, 25); post = pre - rng.normal(2, 1.5, 25)      # normal → t pareado
    w = within_arm_change(list(pre), list(post))
    print(f"      intra-braço (normal): {w['test']}, p={w['p_value']}, Δ={w['mean_change']}")
    expect("diferenças normais → t pareado", w["test"], "t pareado")
    skew = list(rng.exponential(2, 25)); skew2 = list(rng.exponential(2, 25) + 1)  # assimétrico
    bw = between_arms(skew, skew2)
    print(f"      entre braços (assimétrico): {bw['test']}, p={bw['p_value']}")
    expect("assimétrico → Mann-Whitney", bw["test"], "Mann-Whitney U")
    ct = categorical([[1, 9], [6, 4]])   # 2x2 com esperadas pequenas → Fisher
    print(f"      categórico (2x2, esperadas pequenas): {ct['test']}, p={ct['p_value']}")
    expect("2x2 com esperada <5 → Fisher", ct["test"], "Fisher exato")

    print("\n" + "=" * 72)
    print("RESULTADO:", "TODOS OS TESTES APROVADOS ✓" if ok else "HÁ FALHAS ✗")
    print("(números de exemplo são sintéticos e não representam resultados do estudo)")
    print("=" * 72)
