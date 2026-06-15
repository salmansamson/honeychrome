/*
 * af_kernel.c
 * -----------
 * Joint covariance-weighted L1 fluorophore x L2 residual AF assignment kernel.
 *
 * For each cell b, finds the AF variant index j (0-based) that minimises:
 *
 *   score(b, j) = (e_fluor(b,j) / base_e_fluor(b))
 *               * (e_resid(b,j)  / base_e_resid(b))
 *
 * where:
 *   e_fluor(b,j) = sum_f  w[f] * |init_fluor[b,f] - K[b,j] * v_library[f,j]|
 *
 * All 2-D arrays are C-contiguous (row-major).
 * Parallelised over cells with OpenMP.
 *
 * Compile (Linux/macOS):
 *   gcc -O3 -march=native -ffast-math -fopenmp -shared -fPIC \
 *       -o af_kernel.so af_kernel.c -lm
 *
 * On macOS with Apple Clang (no -fopenmp by default), either use
 * libomp from Homebrew or compile without -fopenmp for single-threaded:
 *   clang -O3 -march=native -ffast-math -shared -fPIC \
 *       -o af_kernel.dylib af_kernel.c -lm
 */

#include <stdint.h>
#include <math.h>

#ifdef _OPENMP
#include <omp.h>
#endif

/*
 * joint_cov_l1_argmin
 *
 * Parameters (all arrays C-contiguous float64 / int32)
 * ----------
 * init_fluor   : (B, n_fluors)  initial OLS unmixed values
 * K            : (B, n_af)      per-cell AF scale estimates
 * v_library    : (n_fluors, n_af) AF spectra projected into fluor space
 * w            : (n_fluors,)    covariance-derived L1 weights
 * base_e_fluor : (B,)           per-cell fluor error baseline
 * e_resid      : (B, n_af)      precomputed L2 residual errors
 * base_e_resid : (B,)           per-cell residual baseline
 * best_j       : (B,)  [OUT]    0-based index of best AF variant per cell
 * B            : number of cells in this chunk
 * n_fluors     : number of fluorophore channels
 * n_af         : number of AF variant candidates
 */
void joint_cov_l1_argmin(
    const double * restrict init_fluor,
    const double * restrict K,
    const double * restrict v_library,
    const double * restrict w,
    const double * restrict base_e_fluor,
    const double * restrict e_resid,
    const double * restrict base_e_resid,
    int32_t      * restrict best_j,
    int B,
    int n_fluors,
    int n_af
)
{
    #ifdef _OPENMP
    #pragma omp parallel for schedule(static)
    #endif
    for (int b = 0; b < B; b++) {
        const double bef = base_e_fluor[b];
        const double ber = base_e_resid[b];
        double min_score = 1e300;
        int    best      = 0;

        for (int j = 0; j < n_af; j++) {
            const double k_j = K[b * n_af + j];

            /* Covariance-weighted L1 fluorophore error */
            double ef = 0.0;
            for (int f = 0; f < n_fluors; f++) {
                double d = init_fluor[b * n_fluors + f]
                           - k_j * v_library[f * n_af + j];
                ef += w[f] * fabs(d);
            }

            double score = (ef / bef) * (e_resid[b * n_af + j] / ber);
            if (score < min_score) {
                min_score = score;
                best      = j;
            }
        }

        best_j[b] = best;
    }
}
