// Minimal Icarus compatibility package for compiling the selected common_cells
// benchmark modules. The upstream cc_pkg contains unrelated aggregate literals
// that Icarus 12 cannot parse; these cases only require these width helpers.
package cc_pkg;
  typedef enum logic {
    LZC_TRAILING_ZERO_CNT = 1'b0,
    LZC_LEADING_ZERO_CNT = 1'b1
  } lzc_mode_e;

  function automatic integer unsigned idx_width(input integer unsigned num_idx);
    if (num_idx > 1) idx_width = $clog2(num_idx);
    else idx_width = 1;
  endfunction

  function automatic integer unsigned cnt_width(input integer unsigned num);
    cnt_width = idx_width(num + 1);
  endfunction
endpackage
