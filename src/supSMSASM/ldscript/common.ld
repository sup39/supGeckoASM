SECTIONS {
  . = DEFINED($$) ? $$ : 0x817f9800;
  .text : ALIGN(4) { *(.text) }
  .rodata : ALIGN(4) { *(.rodata) }
}
