// core_joint_unmix.cpp
// ---------------------------------------------------------------------------
// See core_joint_unmix.hpp for the interface contract and scoping notes.
//
// This is a line-by-line port of the algorithm in
// unmix_autospectral_joint_pipeline.cpp's unmix_autospectral_joint_cpp()
// (Sections 1-3). The only substantive changes are:
//   - Rcpp::List variants_list/delta_list -> std::vector<FluorVariantInput>
//   - Rcpp::CharacterVector fluor_names   -> std::vector<std::string>
//   - Rcpp::Nullable<NumericVector> noise_floor -> const arma::vec* (nullable)
//   - Rcpp::stop(...)                    -> std::invalid_argument
// The numerical algorithm itself (Sections 1, 2, 2B, 3, and the per-cell
// joint variant-selection loop) is unchanged.
// ---------------------------------------------------------------------------
#include "core_joint_unmix.hpp"

#include <algorithm>
#include <cmath>
#include <map>
#include <stdexcept>
#include <utility>

#ifdef _OPENMP
#include <omp.h>
#endif

using namespace arma;

namespace {

double quantile_type7(arma::vec x, double p) {
  const uword n = x.n_elem;
  if (n <= 1) return n == 1 ? x[0] : 0.0;
  x = arma::sort(x);
  const double h  = (n - 1) * p;
  const uword  lo = (uword)std::floor(h);
  const uword  hi = std::min(lo + 1, n - 1);
  return x[lo] + (h - lo) * (x[hi] - x[lo]);
}

// ---------------------------------------------------------------------------
// Precomputed data for a single optimisable endmember
// ---------------------------------------------------------------------------
struct FluorPrecomp {
  bool    active     = false;
  int     master_idx = -1;

  mat  v_mats;      // n_variants x D  – candidate mixing matrix
  mat  delta;       // n_variants x D  – (v_mats - master_row), pre-centred

  // Leakage prediction via the other-endmember pseudoinverse
  mat  v_lib;       // (F-1) x n_variants – how each variant leaks into others
  vec  w_leakage;   // F-1               – per-other-endmember cov-propagated weights

  // Rank-1 residual update helpers
  mat  r_lib;       // D x n_variants  – residual component of each variant delta
  mat  r_lib_sq;    // D x n_variants  – r_lib .* r_lib (for weighted self-dots)
  vec  r_dots;      // n_variants      – dot(r_lib(:,v), r_lib(:,v))

  uword n_variants = 0;
};

}  // namespace

arma::mat unmix_autospectral_joint_core(
    arma::mat                              raw_data_in,
    const arma::mat&                       spectra,
    const arma::mat&                       af_spectra,
    const std::vector<std::string>&        fluor_names,
    const arma::vec&                       pos_thresholds,
    const std::vector<FluorVariantInput>&  variants,
    int    n_passes,
    int    n_threads,
    bool   cell_weight,
    const arma::vec* noise_floor,
    double alpha,
    double collinear_thresh,
    bool   joint_pair_resolution,
    int    n_af_passes,
    double refine_af_quantile
) {
  mat raw_data = raw_data_in.t();   // D x N
  const uword N   = raw_data.n_cols;
  const uword F   = spectra.n_rows;
  const uword D   = spectra.n_cols;
  const uword nAF = af_spectra.n_rows;

  if (n_af_passes < 1)
    throw std::invalid_argument("n_af_passes must be >= 1.");
  if (refine_af_quantile < 0.0 || refine_af_quantile > 1.0)
    throw std::invalid_argument("refine_af_quantile must be between 0 and 1.");

  // Noise floor: nullptr/empty -> fill 125.0 everywhere; length-1 -> broadcast.
  arma::vec current_noise_floor;
  if (noise_floor != nullptr && !noise_floor->is_empty())
    current_noise_floor = *noise_floor;
  if (current_noise_floor.is_empty()) {
    current_noise_floor.set_size(D);
    current_noise_floor.fill(125.0);
  } else if (current_noise_floor.n_elem == 1) {
    double scalar_floor = current_noise_floor[0];
    current_noise_floor.set_size(D);
    current_noise_floor.fill(scalar_floor);
  }

  // =========================================================================
  // SECTION 1 – Global pre-computations
  // =========================================================================

  // Global weight vector: 1 / max(mean detector signal, noise_floor).
  // raw_data is D x N, so mean over columns gives a D-vector.
  vec w_global(D);
  vec sqrt_w_global(D);
  if (cell_weight) {
    const vec col_means = mean(raw_data, 1);
    for (uword d = 0; d < D; ++d) {
      w_global[d]      = 1.0 / std::max(col_means[d], current_noise_floor[d]);
      sqrt_w_global[d] = std::sqrt(w_global[d]);
    }
  } else {
    w_global.ones();
    sqrt_w_global.ones();
  }

  // Global weighted pseudoinverse P_w = (S W S^T)^{-1} S W, shape F x D.
  const mat spectra_w  = spectra.each_row() % sqrt_w_global.t();  // F x D
  const mat SST_global = spectra_w * spectra_w.t();               // F x F, constant across cells whenever cell_weight == false
  mat P = solve(SST_global, spectra_w);                            // F x D
  P.each_row() %= sqrt_w_global.t();

  // AF helpers — computed in weighted detector space
  const mat v_lib_af  = P * af_spectra.t();                        // F   x nAF
  const mat r_lib_af  = af_spectra.t() - spectra.t() * v_lib_af;  // D   x nAF

  vec r_dots_af(nAF);
  for (uword j = 0; j < nAF; ++j) {
    const vec r_w = r_lib_af.col(j) % sqrt_w_global;
    r_dots_af[j] = std::max(dot(r_w, r_w), 1e-10);
  }

  // r_lib_af pre-scaled by w_global^2, so the per-cell k_j numerator for
  // every AF candidate collapses into a single gemv instead of nAF dot()s.
  const mat r_lib_af_w2 = r_lib_af.each_col() % (w_global % w_global);

  // Unweighted self-dot of each AF candidate's residual direction, needed
  // for the rank-1 residual-norm update in the vectorised scorer below.
  const rowvec r_dots_af_raw_row = sum(r_lib_af % r_lib_af, 0);
  const vec    r_dots_af_raw     = r_dots_af_raw_row.t();

  // Covariance-propagated AF endmember weights.
  const mat af_cov_mat = mat(P * cov(af_spectra) * P.t());
  const vec w_af = sqrt(abs(af_cov_mat.diag())) + 1e-8;

  // Determine whether endmember variant optimisation is requested.
  const bool af_only = (variants.size() == 0);

  // =========================================================================
  // SECTION 2 – Per-endmember pre-computations
  // =========================================================================

  std::map<std::string, int> name_to_idx;
  for (size_t i = 0; i < fluor_names.size(); ++i)
    name_to_idx[fluor_names[i]] = (int)i;

  const int n_opt = af_only ? 0 : (int)variants.size();
  std::vector<FluorPrecomp> precomp(n_opt);
  std::vector<int> active_indices;

  if (!af_only) {
    for (int i = 0; i < n_opt; ++i) {
      const std::string& fname = variants[i].name;
      if (!name_to_idx.count(fname)) continue;

      FluorPrecomp& pc = precomp[i];
      pc.active     = true;
      pc.master_idx = name_to_idx[fname];
      pc.v_mats     = variants[i].v_mats;
      pc.n_variants = pc.v_mats.n_rows;
      if (pc.n_variants == 0) { pc.active = false; continue; }

      const rowvec master_row = spectra.row(pc.master_idx);

      pc.delta.set_size(pc.n_variants, D);
      for (uword v = 0; v < pc.n_variants; ++v)
        pc.delta.row(v) = pc.v_mats.row(v) - master_row;

      // Other-endmember pseudoinverse
      uvec keep(F - 1); uword ri = 0;
      for (uword r = 0; r < F; ++r) {
        if ((int)r != pc.master_idx) keep[ri++] = r;
      }

      const mat S_nof = spectra.rows(keep);             // (F-1) x D
      const mat U_nof = solve(S_nof * S_nof.t(), S_nof); // (F-1) x D

      pc.v_lib = U_nof * pc.delta.t();   // (F-1) x n_variants

      // Covariance-propagated leakage weights.
      // add a ridge (1e-4 * I) to stabilise small delta samples.
      {
        const mat& delta_obs = variants[i].delta_obs;    // n_variants x D
        mat delta_cov   = cov(delta_obs);
        delta_cov.diag() += 1e-4;                        // ridge regularisation
        const mat leakage_cov = mat(U_nof * delta_cov * U_nof.t()); // force eval
        pc.w_leakage = sqrt(abs(leakage_cov.diag())) + 1e-8;
      }

      // Rank-1 residual update helpers
      // r_lib(:,v) = delta(v)^T - S^T * (P * delta(v)^T)
      pc.r_lib  = pc.delta.t() - spectra.t() * (P * pc.delta.t());  // D x n_variants
      pc.r_lib_sq = pc.r_lib % pc.r_lib;                            // D x n_variants

      pc.r_dots.set_size(pc.n_variants);
      for (uword v = 0; v < pc.n_variants; ++v)
        pc.r_dots[v] = dot(pc.r_lib.col(v), pc.r_lib.col(v));

      active_indices.push_back(i);
    }
  }

  // =========================================================================
  // SECTION 2B – Structural collinearity precompute
  // =========================================================================
  arma::umat is_collinear(F, F, fill::zeros);
  if (!af_only) {
    const int n_active_pre = (int)active_indices.size();
    for (int a = 0; a < n_active_pre; ++a) {
      for (int b = a + 1; b < n_active_pre; ++b) {
        const int fa = precomp[active_indices[a]].master_idx;
        const int fb = precomp[active_indices[b]].master_idx;
        const double c = std::abs(dot(P.row(fa), P.row(fb))) /
          (norm(P.row(fa)) * norm(P.row(fb)) + 1e-12);
        if (c > collinear_thresh) {
          is_collinear(fa, fb) = 1;
          is_collinear(fb, fa) = 1;
        }
      }
    }
  }

  // =========================================================================
  // SECTION 3 – parallel loop
  // =========================================================================
  mat result(N, F + 2, fill::zeros);
  vec  af_abundance_vec(N, fill::zeros);
  uvec af_index_vec(N, fill::zeros);
  mat  resid_mat(D, N, fill::zeros);
  uvec still_active(N, fill::zeros);
  double af_refine_cutoff = 0.0;

#ifdef _OPENMP
  omp_set_num_threads(n_threads);
#endif

#pragma omp parallel
{
  // Thread-local buffers
  vec resid(D);
  vec resid_raw(D);
  vec fluor_unmixed(F);
  mat cell_S(F + 1, D);
  mat cell_S_F_w(F, D);
  vec unmixed_full(F + 1);
  vec sqrt_w(D);
  vec dr(D);
  std::vector<int> best_v(n_opt, -1);
  vec init_f(F);
  vec base_resid_af(D);
  vec cell_resid(D);
  vec y_hat(D);
  vec k_af_vec(nAF);
  vec cross_af(nAF);
  vec resid_sq_af(nAF);
  vec presid_af(nAF);
  vec pfluor_af(nAF);
  vec score_af_vec(nAF);
  mat diffs_af(F, nAF);
  vec coeff_init(F);
  vec other_unmixed(F > 0 ? F - 1 : 0);
  vec trial_unmixed(F);
  vec trial_resid_raw(D);
  vec trial_resid(D);
  mat S_F_w(F, D);

  // Scratch for the vectorised joint-variant scan (Section C).
  vec rsw(D);        // resid .* sqrt_w        (recomputed per pass)
  vec w_eff(D);      // sqrt_w .* sqrt_w       (per cell, weighted path only)
  vec cross_v;       // <resid, (r_v - r_cur).*w>  for all v
  vec drsq_v;        // ||(r_v - r_cur).*w||^2      for all v
  vec g_cur;         // <r_v.*w, r_cur.*w>          for all v
  // Weighted self-dots q_a[v] = ||r_v .* w||^2, cached per active endmember
  // per cell and reused across passes (weighted path only; unweighted uses the
  // static precomputed r_dots). Lazy so below-threshold endmembers cost nothing.
  std::vector<vec>  q_by_active(active_indices.size());
  std::vector<char> q_ready(active_indices.size());

  struct Candidate { double score; int f_opt; uword v; };
  std::vector<Candidate> candidates;

  // committed_deltas now also carries the identity (f_opt, variant) of the
  // committed candidate so a later conflicting candidate can be logged
  // against a known winner, not just an anonymous direction vector.
  struct CommittedDelta { vec dr; double norm; int ai; uword v; };
  std::vector<bool>                  committed;
  std::vector<CommittedDelta>        committed_deltas;
  std::vector<std::pair<int, uword>> commits;
  committed.reserve(n_opt);
  committed_deltas.reserve(n_opt);
  commits.reserve(n_opt);

  // Queued joint-pair retries for the current pass: candidates discarded for
  // conflicting with a structurally-collinear committed candidate. Cleared
  // and rebuilt every pass, since candidates themselves are regenerated
  // fresh each pass.
  struct QueuedRetry { int opt_i; uword v; };
  std::vector<QueuedRetry> queued_retries;

  auto score_af = [&](const vec& active_raw, uword& out_j, double& out_k) -> double {
    init_f        = P * active_raw;
    base_resid_af = active_raw - spectra.t() * init_f;
    const double base_resid_sq   = std::max(dot(base_resid_af, base_resid_af), 1e-16);
    const double base_resid_norm = std::sqrt(base_resid_sq);
    const double base_fluor_l1   = std::max(dot(w_af, abs(init_f)), 1e-8);

    // k_j for every AF candidate in one gemv (was nAF separate dot()s).
    k_af_vec = clamp(r_lib_af_w2.t() * active_raw, 0.0, arma::datum::inf) / r_dots_af;

    // Rank-1 residual-norm update for every candidate at once — avoids
    // forming a D-length r_j per candidate.
    cross_af    = r_lib_af.t() * base_resid_af;
    resid_sq_af = base_resid_sq - 2.0 * (k_af_vec % cross_af)
      + (k_af_vec % k_af_vec % r_dots_af_raw);
    presid_af   = sqrt(clamp(resid_sq_af, 0.0, arma::datum::inf)) / base_resid_norm;

    // Weighted-L1 fluorophore-leakage term for every candidate at once.
    diffs_af = v_lib_af.each_row() % k_af_vec.t();
    diffs_af.each_col() -= init_f;
    pfluor_af = (w_af.t() * abs(diffs_af)).t() / base_fluor_l1;

    score_af_vec = presid_af % pfluor_af;

    const uword best_j = score_af_vec.index_min();
    out_j = best_j;
    out_k = k_af_vec[best_j];
    return score_af_vec[best_j];
  };

#pragma omp for schedule(dynamic, 64)
  for (uword i = 0; i < N; ++i) {
    const vec cell_raw = raw_data.col(i);
    uword j_af; double k_af;
    score_af(cell_raw, j_af, k_af);
    af_index_vec[i]     = j_af;
    af_abundance_vec[i] = k_af;
    resid_mat.col(i)    = cell_raw - k_af * af_spectra.row(j_af).t();
  }

#pragma omp single
{
  if (n_af_passes > 1) {
    af_refine_cutoff = quantile_type7(af_abundance_vec, refine_af_quantile);
    for (uword i = 0; i < N; ++i)
      still_active[i] = (af_abundance_vec[i] >= af_refine_cutoff) ? 1u : 0u;
  }
}

for (int af_pass = 1; af_pass < n_af_passes; ++af_pass) {
#pragma omp for schedule(dynamic, 64)
  for (uword i = 0; i < N; ++i) {
    if (!still_active[i]) continue;
    uword j_ref; double k_ref;
    const double score_ref = score_af(resid_mat.col(i), j_ref, k_ref);
    if (score_ref < 1.0) {
      af_abundance_vec[i] += k_ref;
      resid_mat.col(i)    -= k_ref * af_spectra.row(j_ref).t();
    } else {
      still_active[i] = 0;
    }
  }
}

#pragma omp for schedule(dynamic, 64)
  for (uword i = 0; i < N; ++i) {

    const vec cell_raw   = raw_data.col(i);
    cell_resid            = resid_mat.col(i);
    const double k_af     = af_abundance_vec[i];
    const uword best_j_af = af_index_vec[i];

    if (cell_weight) {
      S_F_w = spectra;
      S_F_w.each_row() %= sqrt_w_global.t();
      solve(coeff_init, S_F_w.t(), cell_resid % sqrt_w_global, solve_opts::fast);
      y_hat = (spectra.t() * coeff_init) + (cell_raw - cell_resid);
      for (uword d = 0; d < D; ++d)
        sqrt_w[d] = 1.0 / std::sqrt(std::max(std::abs(y_hat[d]), current_noise_floor[d]));

      cell_S_F_w    = spectra.each_row() % sqrt_w.t();
      fluor_unmixed = solve(cell_S_F_w.t(), cell_resid % sqrt_w, solve_opts::fast);
    } else {
      // Detector weights are identical across cells here, so use global P
      sqrt_w.ones();
      cell_S_F_w    = spectra;
      fluor_unmixed = P * cell_resid;
    }

    resid_raw = cell_resid - spectra.t() * clamp(fluor_unmixed, 0.0, datum::inf);
    resid     = resid_raw % sqrt_w;

    // =====================================================================
    // B2. EARLY RETURN
    // =====================================================================
    if (af_only) {
      result(i, span(0, F - 1)) = fluor_unmixed.t();
      result(i, F)               = k_af;
      result(i, F + 1)           = (double)best_j_af + 1.0;
      continue;
    }

    // Only needed for the joint variant-selection pass loop and try_commit's
    // incremental Gram update (Section C) below -- now built *after* the
    // af_only early return rather than before it.
    cell_S.rows(0, F - 1) = spectra;

    mat A_base;
    if (cell_weight) {
      A_base = cell_S_F_w * cell_S_F_w.t();
    } else {
      A_base = SST_global;   // constant across cells; reused from Section 1
    }
    vec b_base = cell_S_F_w * (cell_resid % sqrt_w);
    vec y_vec  = cell_resid % sqrt_w;

    const double cell_resid_ss = dot(cell_resid, cell_resid);
    std::fill(best_v.begin(), best_v.end(), -1);


    // =====================================================================
    // C. JOINT VARIANT SELECTION
    // =====================================================================
    const int n_active = (int)active_indices.size();

    // Effective detector weighting for the residual-space scan.
    //   cell_weight == false -> sw is all ones, so the residual math collapses
    //   onto the statically precomputed r_lib / r_dots (no per-cell build).
    const vec& sw = cell_weight ? sqrt_w : sqrt_w_global;
    if (cell_weight) {
      w_eff = sw % sw;                               // per-cell detector weights
      std::fill(q_ready.begin(), q_ready.end(), 0);  // invalidate q cache
    }

    for (int pass = 0; pass < n_passes; ++pass) {

      const double rss_curr        = std::max(dot(resid, resid), 1e-12);
      const double rss_curr_sqrt   = std::sqrt(rss_curr);
      const double ratio_thresh_sq = 1.1025 * rss_curr;   // (1.05^2) * rss_curr
      double rss_accepted = dot(resid, resid);

      candidates.clear();
      queued_retries.clear();

      // resid weighted once per pass (independent of endmember).
      // <resid, x .* sw> == <resid .* sw, x>, so we fold sw into resid here.
      if (cell_weight) rsw = resid % sw; else rsw = resid;

      for (int ai = 0; ai < n_active; ++ai) {
        const int opt_i      = active_indices[ai];
        const FluorPrecomp& pc = precomp[opt_i];
        const double abund   = fluor_unmixed[pc.master_idx];
        if (abund < pos_thresholds[pc.master_idx]) continue;

        uword oi = 0;
        for (uword r = 0; r < F; ++r)
          if ((int)r != pc.master_idx) other_unmixed[oi++] = fluor_unmixed[r];

        const double base_leakage =
          std::max(dot(pc.w_leakage, abs(other_unmixed)), 1e-8);
        const int cur_v = best_v[opt_i];

        // ---- Vectorised residual-ratio scan over all variants at once ----
        if (cell_weight && !q_ready[ai]) {
          q_by_active[ai] = pc.r_lib_sq.t() * w_eff;
          q_ready[ai] = 1;
        }
        const vec& q_ref = cell_weight ? q_by_active[ai] : pc.r_dots;
        cross_v = pc.r_lib.t() * rsw;                          // n_variants
        if (cur_v < 0) {
          drsq_v = q_ref;
        } else {
          if (cell_weight) g_cur = pc.r_lib.t() * (pc.r_lib.col(cur_v) % w_eff);
          else             g_cur = pc.r_lib.t() *  pc.r_lib.col(cur_v);
          drsq_v  = q_ref + q_ref[cur_v] - 2.0 * g_cur;
          cross_v -= cross_v[cur_v];
        }

        const double abund2 = abund * abund;
        for (uword v = 0; v < pc.n_variants; ++v) {
          const double new_rss =
            rss_curr - 2.0 * abund * cross_v[v] + abund2 * drsq_v[v];
          if (new_rss > ratio_thresh_sq) continue;   // == resid_ratio > 1.05

          double leak_num = 0.0;
          const double* vl = pc.v_lib.colptr(v);
          if (cur_v < 0) {
            for (uword o = 0; o < F - 1; ++o)
              leak_num += pc.w_leakage[o] *
                std::abs(other_unmixed[o] - abund * vl[o]);
          } else {
            const double* vlc = pc.v_lib.colptr(cur_v);
            for (uword o = 0; o < F - 1; ++o)
              leak_num += pc.w_leakage[o] *
                std::abs(other_unmixed[o] - abund * (vl[o] - vlc[o]));
          }
          const double leakage_ratio = leak_num / base_leakage;

          const double resid_ratio =
            std::sqrt(std::max(new_rss, 0.0)) / rss_curr_sqrt;
          const double joint_score =
            std::pow(std::max(resid_ratio,   1e-8), alpha) *
            std::pow(std::max(leakage_ratio, 1e-8), 1.0 - alpha);

          if (joint_score < 1.0)
            candidates.push_back({joint_score, ai, v});
        }
      }

      if (candidates.empty()) break;

      std::sort(candidates.begin(), candidates.end(),
                [](const Candidate& a, const Candidate& b){
                  return a.score < b.score;
                });

      committed.assign(n_active, false);
      committed_deltas.clear();
      commits.clear();

      for (const auto& cand : candidates) {
        if (committed[cand.f_opt]) continue;

        const int opt_i        = active_indices[cand.f_opt];
        const FluorPrecomp& pc = precomp[opt_i];
        const double abund     = fluor_unmixed[pc.master_idx];
        const int cur_v        = best_v[opt_i];

        if (cur_v < 0) {
          dr = pc.r_lib.col(cand.v) * abund;
        } else {
          dr = (pc.r_lib.col(cand.v) - pc.r_lib.col(cur_v)) * abund;
        }
        const double dr_norm = std::max(norm(dr), 1e-12);

        bool conflict = false;
        for (const auto& cd : committed_deltas) {
          const double cosine = std::abs(dot(dr, cd.dr)) /
            (dr_norm * cd.norm);
          if (cosine > 0.5) {
            conflict = true;
            const int winner_master = precomp[active_indices[cd.ai]].master_idx;
            const bool collinear_pair = (bool)is_collinear(pc.master_idx, winner_master);

            if (joint_pair_resolution && collinear_pair) {
              queued_retries.push_back({opt_i, cand.v});
            }
            break;
          }
        }
        if (conflict) continue;

        committed[cand.f_opt] = true;
        committed_deltas.push_back({dr, dr_norm, cand.f_opt, cand.v});
        commits.push_back({opt_i, cand.v});
      }

      if (commits.empty()) break;

      auto try_commit = [&](int opt_i, uword v) -> bool {
        const FluorPrecomp& pc_v = precomp[opt_i];
        const int idx = pc_v.master_idx;

        const rowvec prev_row = cell_S.row(idx);
        cell_S.row(idx) = pc_v.v_mats.row(v);

        rowvec s_new = pc_v.v_mats.row(v) % sqrt_w.t();
        vec col_update = cell_S_F_w * s_new.t();

        mat A_trial = A_base;
        for (uword r = 0; r < F; ++r) {
          A_trial(r, idx) = col_update[r];
          A_trial(idx, r) = col_update[r];
        }
        A_trial(idx, idx) = arma::dot(s_new, s_new);

        vec b_trial = b_base;
        b_trial[idx] = arma::dot(s_new, y_vec);

        bool success = arma::solve(trial_unmixed, A_trial, b_trial,
                                   arma::solve_opts::fast + arma::solve_opts::likely_sympd);
        if (!success) {
          cell_S.row(idx) = prev_row; // Linear dependency fault protection
          return false;
        }

        trial_resid_raw = cell_resid - cell_S.rows(0, F - 1).t() * clamp(trial_unmixed, 0.0, datum::inf);
        trial_resid = trial_resid_raw % sqrt_w;
        const double trial_rss = dot(trial_resid, trial_resid);

        if (trial_rss < rss_accepted) {
          best_v[opt_i] = (int)v;
          fluor_unmixed = trial_unmixed;
          resid_raw     = trial_resid_raw;
          resid         = trial_resid;
          rss_accepted  = trial_rss;

          cell_S_F_w.row(idx) = s_new;
          A_base = A_trial;
          b_base = b_trial;
          return true;
        } else {
          cell_S.row(idx) = prev_row;
          return false;
        }
      };

      for (auto& [opt_i, v] : commits) try_commit(opt_i, v);

      if (joint_pair_resolution) {
        for (const auto& qr : queued_retries)
          try_commit(qr.opt_i, qr.v);
      }

      if (dot(resid_raw, resid_raw) < 1e-16 * cell_resid_ss) break;
    } // end for pass

    // =====================================================================
    // D. Write output
    // =====================================================================
    result(i, span(0, F - 1)) = fluor_unmixed.t();
    result(i, F)               = k_af;
    result(i, F + 1)           = (double)best_j_af + 1.0;
  } // end for i
} // end pragma omp parallel

return result;
}
