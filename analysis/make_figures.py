"""Single entry point: regenerates all four A11 figures from results/*.csv.

Run with: python3 analysis/make_figures.py
"""
import fig1_ablation
import fig2_brackets
import fig3_ttl_tradeoff
import fig4_cache_size
import make_supplementary

if __name__ == "__main__":
    fig1_ablation.main()
    fig2_brackets.main()
    fig3_ttl_tradeoff.main()
    fig4_cache_size.main()
    make_supplementary.main()
