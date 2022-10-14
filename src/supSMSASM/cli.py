# SPDX-License-Identifier: MIT
# Copyright (c) 2022 sup39[サポミク]

import shutil
from distutils import spawn
import tempfile
import os
import subprocess
import sys
import re
from collections import defaultdict, Counter
import logging

import win32clipboard
def pbcopy(content):
  win32clipboard.OpenClipboard()
  win32clipboard.EmptyClipboard()
  win32clipboard.SetClipboardText(content)
  win32clipboard.CloseClipboard()

logger = logging.getLogger('supGeckoCode')

def normalize_dolver(s):
  if re.match(r'^(?:JP?|N(?:TSC)?[-_]?J)(?:1\.?0|\.0)?$|^1\.0$', s):
    return 'NTSC-J_1.0'
  if re.match(r'^(?:JP?A|N(?:TSC)?[-_]?J)(?:1\.?1|\.1|A)?$|^1\.1$', s):
    return 'NTSC-J_1.1'
  #if re.match(r'^EU|P|PAL$', s):
  #  return 'PAL'
  #if re.match(r'^US?|N(?:TSC)?[-_]?U$', s):
  #  return 'NTSC-U'
  return None

def system(argv, *args, **kwargs):
  r = subprocess.run(argv, *args, capture_output=True, text=True, **kwargs)
  if r.stderr: logger.error(r.stderr)
  return r


def asm2gecko(fnIn, dolver):
  __dirname__ = os.path.dirname(__file__)
  includeDir, ldscriptDir = (f'{__dirname__}/{name}' for name in ['include', 'ldscript'])

  distDir = tempfile.mkdtemp()
  distASM, distOBJ, distLOBJ, distBIN = (f'{distDir}/0.{ext}' for ext in ['s', 'o', 'l.o', 'bin'])
  def cleanup():
    shutil.rmtree(distDir)

  try:
    # include macros.inc
    with open(distASM, 'w') as fw, open(fnIn, 'r') as fr:
      print(f'.include "macros.inc"', file=fw)
      for line in fr: fw.write(line)

    # assemble
    if system([
      'powerpc-eabi-as',
      '-o', distOBJ,
      '-I', includeDir,
      distASM,
    ]).returncode: return cleanup()

    # link
    extraLDFlags = []
    extraLDScript = re.sub('\.s', '.ld', fnIn)
    if os.path.isfile(extraLDScript):
      extraLDFlags += ['-T', extraLDScript]
    if system([
      'powerpc-eabi-ld',
      '-o', distLOBJ,
      '-T', f'{ldscriptDir}/{dolver}.ld',
      *extraLDFlags,
      '-T', f'{ldscriptDir}/common.ld',
      distOBJ,
    ]).returncode: return cleanup()

    # binary
    if system([
      'powerpc-eabi-objcopy',
      '-O', 'binary',
      distLOBJ, distBIN,
    ]).returncode: return cleanup()

    # gecko symbols
    asmSymbs = {}
    geckoSymbs = {}
    r = system([
      'powerpc-eabi-objdump',
      '-h', '-t', distLOBJ,
    ])
    lines = r.stdout.split('\n')
    geckoBase = int(lines[5].split()[3], 16)
    isC2 = False
    for line in lines[8:]:
      if not re.match('^[0-9a-f]{8} \w', line): continue
      cols = line.split()
      if len(cols) != 5: continue
      addr, _, sec, _, name = cols
      if sec == '.text':
        asmSymbs[name] = addr
      else:
        if name == '$$' and int(addr, 16) == 0:
          isC2 = True
        m = re.match(r'\$(bl?|C2)\$(.*)', name)
        if m is None: continue
        ct, name = m.groups()
        if name in geckoSymbs:
          logger.error('Conflict symbols: $%s$, $%s$ for `%s`'%(
            geckoSymbs[name][0], ct, name,
          ))
          return cleanup()
        geckoSymbs[name] = (ct, addr)

    # binary
    if system([
      'powerpc-eabi-objcopy',
      '-O', 'binary',
      distLOBJ, distBIN,
    ]).returncode: cleanup()
    with open(distBIN, 'rb') as f:
      codeBin = f.read()

    # make code
    codes = []
    codeSymbs = []
    append_code = lambda a, b: codes.append('%08X %08X'%(a, b))
    append_hex_code = lambda a, b: codes.append(('%s %s'%(a, b)).upper())
    def dump_bin_code(raw):
      for a, b in re.findall(r'(.{8})(.{8})', raw.hex()):
        append_hex_code(a, b)

    if len(geckoSymbs) == 0:
      # C0
      if len(codeBin)&4: codeBin += b'\x4E\x80\x00\x20'
      append_code(0xC0000000, len(codeBin)>>3)
      dump_bin_code(codeBin)
    elif isC2:
      # C2
      ## calc size of each C2 code
      sizes = {}
      pairs = sorted((asmSymbs[name], name) for name, addr in geckoSymbs.items() if name in asmSymbs)
      for (addr, name), (addr1, name1) in zip(pairs, pairs[1:]):
        sizes[name] = int(addr1, 16)-int(addr, 16)
      addr, name = pairs[-1]
      sizes[name] = len(codeBin)-int(addr, 16)
      ## make code
      for name, (ct, src) in geckoSymbs.items():
        if ct != 'C2': continue
        dst = asmSymbs.get(name, None)
        if dst is None: continue
        size = sizes[name]
        src = int(src, 16)
        dst = int(dst, 16)
        c0 = 0xC200_0000 | src&0x01ff_ffff
        c1 = (size>>3)+1
        append_code(c0, c1)
        ## dump code
        code = codeBin[dst:dst+size]
        if size & 4 == 0: code += b'\x60\x00\x00\x00'
        code += b'\x00\x00\x00\x00'
        dump_bin_code(code)
    else:
      ## 04 b/bl code
      for name, (ct, src) in geckoSymbs.items():
        if ct not in ['b', 'bl']: continue
        dst = asmSymbs.get(name, None)
        if dst is not None:
          src = int(src, 16)
          dst = int(dst, 16)
          c0 = 0x0400_0000 | src&0x01ff_ffff
          c1 = (0x4C000000 if dst<src else 0x48000000) + \
            (dst-src) + (1 if ct == 'bl' else 0)
          append_code(c0, c1)
          codeSymbs.append((name, ct, src, dst))
      ## 06 bin code
      if len(codeBin):
        append_code(0x0600_0000 | geckoBase&0x01ff_ffff, len(codeBin))
        dump_bin_code(codeBin+b'\x00'*7)
  except:
    import traceback
    traceback.print_exc()
    return cleanup()

  # DONE
  cleanup()
  return codes, codeSymbs, asmSymbs, isC2

def main():
  logging.basicConfig()

  # check required bin
  for exe in ['powerpc-eabi-as', 'powerpc-eabi-ld', 'powerpc-eabi-objdump', 'powerpc-eabi-objcopy']:
    if spawn.find_executable(exe) is None:
      logger.error('Cannot find powerpc-eabi-{as,ld,objdump,objcopy}')

  argv = sys.argv
  argc = len(argv)
  if argc <= 1:
    logger.error('Usage: %s {*.s} [JP|JPA]'%argv[0])
    sys.exit(1)

  fnIn = argv[1]
  dolver = normalize_dolver(argv[2]) if argc > 2 else 'NTSC-J_1.0'
  if dolver is None:
    logger.error('Unknown dol version: %s'%argv[2])
    sys.exit(1)

  r = asm2gecko(fnIn, dolver)
  if r is not None:
    codes, codeSymbs, asmSymbs, isC2 = r
    pbcopy('\n'.join(codes))
    # print asm symbols
    if not isC2:
      for name, addr in asmSymbs.items():
        print(addr.upper(), name)
      print()
    # print gecko symbols
    for name, ct, src, dst in codeSymbs:
      print('%-2s [%08X] @[%08X] %s'%(ct, dst, src, name))
    print()
    # code length
    print('Code length:', len(codes), 'line(s)')

if __name__ == '__main__':
  main()
