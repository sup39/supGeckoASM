SECTIONS {
  . = DEFINED($$) ? $$ : 0;
  .text : ALIGN(4) { *(.text) }
  .rodata : ALIGN(4) { *(.rodata) }
}
