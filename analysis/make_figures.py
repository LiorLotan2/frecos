"""Single entry point: regenerates all four figures and the supplementary table from
results/*.csv.

Run with: python3 analysis/make_figures.py
"""
import fig1_brackets
import fig2_ablation
import fig3_cache_size
import fig4_ttl_tradeoff
import make_supplementary

if __name__ == "__main__":
    fig1_brackets.main()
    fig2_ablation.main()
    fig3_cache_size.main()
    fig4_ttl_tradeoff.main()
    make_supplementary.main()
