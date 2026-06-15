"""
af_kernel_wrapper.py
--------------------
Python interface to the compiled _af_kernel cffi extension.

Usage
-----
    from af_kernel_wrapper import joint_cov_l1_argmin, AF_KERNEL_AVAILABLE

    if AF_KERNEL_AVAILABLE:
        best_j = joint_cov_l1_argmin(
            init_fluor,    # (B, n_fluors) float64 C-contiguous
            K,             # (B, n_af)     float64 C-contiguous
            v_library,     # (n_fluors, n_af) float64 C-contiguous
            w,             # (n_fluors,)   float64 C-contiguous
            base_e_fluor,  # (B,)          float64 C-contiguous
            e_resid,       # (B, n_af)     float64 C-contiguous
            base_e_resid,  # (B,)          float64 C-contiguous
        )
        # best_j : ndarray (B,) int32, 0-based

The module tries to import _af_kernel from the same directory as this file
(i.e. the compiled cffi extension).  AF_KERNEL_AVAILABLE is False and
joint_cov_l1_argmin raises ImportError if the extension is absent.
"""

import os
import sys
import logging
import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Load the compiled extension
# ---------------------------------------------------------------------------

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

try:
    import _af_kernel as _lib
    AF_KERNEL_AVAILABLE = True
    logger.info('af_kernel_wrapper: compiled C kernel loaded.')
except ImportError:
    _lib = None
    AF_KERNEL_AVAILABLE = False
    logger.info('af_kernel_wrapper: compiled C kernel not found — '
                'run build_af_kernel.py to enable.')


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def joint_cov_l1_argmin(
    init_fluor:   np.ndarray,
    K:            np.ndarray,
    v_library:    np.ndarray,
    w:            np.ndarray,
    base_e_fluor: np.ndarray,
    e_resid:      np.ndarray,
    base_e_resid: np.ndarray,
) -> np.ndarray:
    """
    Call the compiled C joint-cov L1 argmin kernel.

    All inputs must be float64 and C-contiguous.  The caller is responsible
    for ensuring this (use np.ascontiguousarray if needed).

    Returns
    -------
    best_j : ndarray (B,) int32, 0-based variant index per cell.
    """
    if not AF_KERNEL_AVAILABLE:
        raise ImportError(
            'Compiled AF kernel not available. '
            'Run build_af_kernel.py first.'
        )

    ffi = _lib.ffi
    lib = _lib.lib

    B        = init_fluor.shape[0]
    n_fluors = init_fluor.shape[1]
    n_af     = v_library.shape[1]

    best_j = np.empty(B, dtype=np.int32)

    lib.joint_cov_l1_argmin(
        ffi.cast('double *', init_fluor.ctypes.data),
        ffi.cast('double *', K.ctypes.data),
        ffi.cast('double *', v_library.ctypes.data),
        ffi.cast('double *', w.ctypes.data),
        ffi.cast('double *', base_e_fluor.ctypes.data),
        ffi.cast('double *', e_resid.ctypes.data),
        ffi.cast('double *', base_e_resid.ctypes.data),
        ffi.cast('int32_t *', best_j.ctypes.data),
        B,
        n_fluors,
        n_af,
    )

    return best_j
