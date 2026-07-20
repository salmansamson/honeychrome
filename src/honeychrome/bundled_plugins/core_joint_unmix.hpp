// core_joint_unmix.hpp
// ---------------------------------------------------------------------------
// Shared Armadillo-only core for the AutoSpectral joint AF + fluorophore-
// variant per-cell unmixing pipeline.
//
// Extracted from unmix_autospectral_joint_pipeline.cpp's
// unmix_autospectral_joint_cpp() per CONTEXT_AutoSpectral.md §4.1 — all
// Rcpp/RcppArmadillo types (CharacterVector, Rcpp::List, Rcpp::Nullable) have
// been replaced with plain Armadillo/STL types so this file depends only on
// Armadillo and the standard library.
//
// The existing R-side Rcpp wrapper in unmix_autospectral_joint_pipeline.cpp
// is UNCHANGED and does not call this file. This core is wrapped exactly
// once, by autospectral_opt_pybind.cpp, for the Honeychrome Python plugin.
// A matching R-side re-wrap of *this* extracted core (CONTEXT_AutoSpectral.md
// Phase 1) has not been done — see the change document header.
// ---------------------------------------------------------------------------
#pragma once

#include <armadillo>
#include <string>
#include <vector>

// One optimizable fluorophore's variant data, as discovered by
// autospectral_optimization_functions.py::discover_fluor_variants() (Python
// port of get.fluor.variants()) and assembled by
// autospectral_optimization_functions.py::unmix_autospectral_optimization().
struct FluorVariantInput {
  std::string name;        // fluorophore label, must match a row of `spectra`
  arma::mat    v_mats;      // n_variants x D — candidate mixing (spectrum) matrix
  arma::mat    delta_obs;   // n_variants x D — (v_mats - reference row); same
                             // quantity as R's delta.list[[fl]] (get_spectral_variants.R
                             // line ~481), used for the covariance-propagated
                             // leakage weight, NOT a separate per-event sample.
};

// Joint per-cell AF + fluorophore-variant unmixing (CONTEXT_AutoSpectral.md
// §2.3). Sections 1-3 of the original unmix_autospectral_joint_cpp() are
// unchanged; only the Rcpp-specific input marshalling has been removed.
//
// Parameters
// ----------
// raw_data_in      : N x D  — raw fluorescence events (row-major on the caller
//                     side; transposed internally to D x N for the per-cell loop).
// spectra          : F x D  — reference fluorophore spectra (no AF row).
// af_spectra       : nAF x D — AF candidate spectra, nAF >= 2.
// fluor_names      : length F, row order matching `spectra`.
// pos_thresholds   : length F — per-fluorophore unmixed-space positivity
//                     threshold, gates whether joint variant optimisation is
//                     attempted for a cell (see Section 3, step C).
// variants         : one entry per *optimizable* fluorophore. Empty vector ->
//                     AF-only mode (no joint variant optimisation, matches
//                     the original `af_only` early-return path).
// n_passes         : joint variant-optimisation passes per cell (default 1,
//                     per the updated R/Honeychrome-shared default).
// n_threads        : OpenMP thread count.
// cell_weight      : per-cell detector weighting on/off.
// noise_floor      : nullptr or empty -> fill 125.0 everywhere; length 1 ->
//                     broadcast that scalar to all D detectors; length D ->
//                     used as-is. Mirrors the original Rcpp::Nullable handling.
// alpha            : residual-vs-leakage balance in the joint score.
// collinear_thresh : cosine threshold for structurally-collinear fluorophore
//                     pairs (Section 2B).
// joint_pair_resolution : retry conflicting candidates against collinear
//                     partners after the first commit pass.
// n_af_passes      : AF refinement passes per cell.
// refine_af_quantile : fraction of cells carried into extra AF passes.
//
// Returns
// -------
// N x (F+2) matrix: [fluor_1 .. fluor_F | AF abundance | AF index (1-based)].
arma::mat unmix_autospectral_joint_core(
    arma::mat                              raw_data_in,
    const arma::mat&                       spectra,
    const arma::mat&                       af_spectra,
    const std::vector<std::string>&        fluor_names,
    const arma::vec&                       pos_thresholds,
    const std::vector<FluorVariantInput>&  variants,
    int                                     n_passes               = 1,
    int                                     n_threads               = 1,
    bool                                    cell_weight             = false,
    const arma::vec*                       noise_floor             = nullptr,
    double                                  alpha                   = 0.5,
    double                                  collinear_thresh        = 0.5,
    bool                                    joint_pair_resolution   = true,
    int                                     n_af_passes             = 1,
    double                                  refine_af_quantile      = 0.5
);
