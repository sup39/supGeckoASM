# supSMSASM
A tool to make Gecko code from ASM for SMS

This tool only runs on Windows currently.

## Installation
First, install [devkitPro](https://github.com/devkitPro/installer/releases).

Then, use pip to install supSMSASM:
```
pip install supSMSASM
```

## Usage
This tool can make C0, C2, and Fixed-Location-C2 code from ASM code.
See [Supported Code Type](#supported-code-type) for more information.

With all files prepared, use the following command to generate the Gecko code:
```
supSMSASM {*.s} [JP|JPA]
```

The generated code will be copied to your clipboard.

## Symbols
Symbols defined in [ldscript/](src/supSMSASM/ldscript) can be used in `*.s` and `*.ld`.

## Supported Code Type
### C0
Simply write your ASM code in `*.s` and use `supSMSASM` to convert it into Gecko code.

### C2
You will need the following two files:
- `*.s`: ASM source code
- `*.ld`: LD script for defining the entry points of C2. You need to define a symbol `$$` and set the value to `0`.

To define a C2 entry,
define a symbol with `$C2$` prepending to the symbol defined in `*.s` file.

For example, to make 2 C2 codes, first write the body of the code in your `xxx.s` file:
```asm
SomeC2Code:
  # ...

AnotherC2Code:
  # ...
```

Then, in your `xxx.ld` file, define the entry points:
```ld
/* The following line is required for C2 code type */
$$ = 0;

$C2$SomeC2Code = 0x80345678;
$C2$AnotherC2Code = 0x80DEFABC;
```

Finally, use `supGeckoCode xxx.s` to generate Gecko code.
The result will be like:
```
C2345678 XXXXXXXX
... (instructions in SomeC2Code)
C2DEFABC XXXXXXXX
... (instructions in AnotherC2Code)
```

Note that you can't branch to absolute address with `bl` or `b` directly
since the location of the code is unknown.
You will need to set the destination to register and use `blr`, `bctr` etc. instead.

### Fixed-Location-C2
To solve the problem that `C2` code type can't branch to absolute address directly,
you can use `06` to place the code into a fixed location
and then use `04` to replace the instruction with `b` or `bl` to the code.

You will need the following two files (same as C2):
- `*.s`: ASM source code
- `*.ld`: LD script for defining the entry points and the address to place the code

To define a entry,
define a symbol with `$b$` or `$bl$` prepending to the symbol defined in `*.s` file.
This will replace the instruction at the given address with `b` or `bl` to the the symbol.

For example, to make 2 Fixed-Location-C2 codes, first write the body of the code in your `xxx.s` file:
```asm
SomeCodeWithB:
  b $b$SomeCodeWithB+4

AnotherCodeWithBL:
  # ...
  blr
```

Then, in your `xxx.ld` file, define the entry points:
```ld
/* The following line defines the address to place the code.
   It will be 0x817F9800 if you don't specify */
$$ = 0x817F9800;

$b$SomeCodeWithB = 0x80345678;
$bl$AnotherCodeWithBL = 0x80DEFABC;
```

Finally, use `supGeckoCode xxx.s` to generate Gecko code.
The result will be like:
```
04345678 494B4188 <-- b from 80345678 to SomeCodeWithB
04DEFABC 48A09D49 <-- bl from 80DEFABC to AnotherCodeWithBL
077F9800 XXXXXXXX
... (instructions in SomeCodeWithB and AnotherCodeWithBL)
```

Note that unlike C2, you have to explicitly do `b` or `blr` back to the original program.
In addition, just like C2, you have to put the original instruction manually if needed.
