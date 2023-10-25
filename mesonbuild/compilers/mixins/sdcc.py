# Copyright 2023 The meson development team
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import annotations

"""Abstraction for Small Device C Compiler (SDCC) family of compilers.
"""

import os
import subprocess
import typing as T

from ... import coredata
from ... import mlog
from ... import mesonlib
from ...mesonlib import EnvironmentException, OptionKey
from ..compilers import CompileCheckMode, Compiler
from ...environment import Environment

class SdccCompiler(Compiler):

    id = 'sdcc'

    BUILDTYPE_ARGS: T.Dict[str, T.List[str]] = {
        'plain': [],
        'debug': [],
        'debugoptimized': [],
        'release': [],
        'minsize': [],
        'custom': [],
    }

    OPTIMIZATION_ARGS: T.Dict[str, T.List[str]] = {
        'plain': [],
        '0': [],
        'g': [],
        '1': ['--opt-code-speed'],
        '2': ['--opt-code-speed'],
        '3': ['--opt-code-speed'],
        's': ['--opt-code-size'],
    }

    DEBUG_ARGS: T.Dict[bool, T.List[str]] = {
        False: [],
        True: ['--debug']
    }

    def __init__(self):
        if not self.is_cross:
            raise EnvironmentException('sdcc supports only cross-compilation.')

        self.base_options = {OptionKey(o) for o in ['b_ndebug']}

    def get_always_args(self) -> T.List[str]:
        return []

    def get_options(self) -> 'coredata.MutableKeyedOptionDictType':
        stds = ['none']
        stds += ['c89', 'c90', 'c95', 'c99', 'c11', 'c17', 'c18', 'c2x', 'c23']
        stds += ['iso9899:1990', 'iso9899:199409', 'iso9899:1999', 'iso9899:2011', 'iso9899:2017', 'iso9899:2018']
        stds += ['sdcc89', 'sdcc90', 'sdcc99', 'sdcc11', 'sdcc17', 'sdcc18', 'sdcc2x', 'sdcc23']

        opts = super().get_options()
        opts.update({
            OptionKey('std', machine=self.for_machine, lang=self.language): coredata.UserComboOption(
                'C language standard to use',
                stds,
                'none',
            )
        })
        return opts

    def get_no_stdinc_args(self) -> T.List[str]:
        return ['--nostdinc']

    def get_no_stdlib_link_args(self) -> T.List[str]:
        return ['--nostdlib']

    def get_buildtype_args(self, buildtype: str) -> T.List[str]:
        return self.BUILDTYPE_ARGS[buildtype]

    def get_include_args(self, path: str, is_system: bool) -> T.List[str]:
        if path == '':
            path = '.'
        return ['-I' + path]

    def get_pic_args(self) -> T.List[str]:
        # sdcc doesn't support PIC
        return []

    def get_preprocess_only_args(self) -> T.List[str]:
        return ['-E']

    def get_largefile_args(self) -> T.List[str]:
        return []

    def get_werror_args(self) -> T.List[str]:
        return ['--Werror']

    def get_warn_args(self, level: str) -> T.List[str]:
        return []

    def get_optimization_args(self, optimization_level: str) -> T.List[str]:
        return self.OPTIMIZATION_ARGS[optimization_level]

    def get_no_optimization_args(self) -> T.List[str]:
        return []

    def get_debug_args(self, is_debug: bool) -> T.List[str]:
        return self.DEBUG_ARGS[is_debug]

    def get_no_warn_args(self) -> T.List[str]:
        return []

    def get_preprocessor(self) -> Compiler:
        raise NotImplementedError(f'get_preprocessor not implemented for {self.get_id()}')

    def compute_parameters_with_absolute_paths(self, parameter_list: T.List[str], build_dir: str) -> T.List[str]:
        for idx, i in enumerate(parameter_list):
            if i[:2] == '-I' or i[:2] == '-L':
                parameter_list[idx] = i[:2] + os.path.normpath(os.path.join(build_dir, i[2:]))

        return parameter_list

    def _sanity_check_impl(self, work_dir: str, environment: 'Environment',
                           sname: str, code: str) -> None:
        """Check if the compiler can compile a program.

        Implementation copied from CLikeCompiler but for some reason the sdcc
        compiler won't accept .exe in output filename.
        """
        mlog.debug('Sanity testing ' + self.get_display_language() + ' compiler:', mesonlib.join_args(self.exelist))
        mlog.debug(f'Is cross compiler: {self.is_cross!s}.')

        source_name = os.path.join(work_dir, sname)
        binname = sname.rsplit('.', 1)[0]
        mode = CompileCheckMode.LINK
        if self.is_cross:
            binname += '_cross'
            if self.exe_wrapper is None:
                # Linking cross built C/C++ apps is painful. You can't really
                # tell if you should use -nostdlib or not and for example
                # on OSX the compiler binary is the same but you need
                # a ton of compiler flags to differentiate between
                # arm and x86_64. So just compile.
                mode = CompileCheckMode.COMPILE
        cargs, largs = self._get_basic_compiler_args(environment, mode)
        extra_flags = cargs + self.linker_to_compiler_args(largs)

        # Is a valid executable output for sdcc
        binname += '.out'
        # Write binary check source
        binary_name = os.path.join(work_dir, binname)
        with open(source_name, 'w', encoding='utf-8') as ofile:
            ofile.write(code)
        # Compile sanity check
        # NOTE: extra_flags must be added at the end. On MSVC, it might contain a '/link' argument
        # after which all further arguments will be passed directly to the linker
        cmdlist = self.exelist + [sname] + self.get_output_args(binname) + extra_flags
        pc, stdo, stde = mesonlib.Popen_safe(cmdlist, cwd=work_dir)
        mlog.debug('Sanity check compiler command line:', mesonlib.join_args(cmdlist))
        mlog.debug('Sanity check compile stdout:')
        mlog.debug(stdo)
        mlog.debug('-----\nSanity check compile stderr:')
        mlog.debug(stde)
        mlog.debug('-----')
        if pc.returncode != 0:
            raise mesonlib.EnvironmentException(f'Compiler {self.name_string()} cannot compile programs.')
        # Run sanity check
        if self.is_cross:
            if self.exe_wrapper is None:
                # Can't check if the binaries run so we have to assume they do
                return
            cmdlist = self.exe_wrapper.get_command() + [binary_name]
        else:
            cmdlist = [binary_name]
        mlog.debug('Running test binary command: ', mesonlib.join_args(cmdlist))
        try:
            # fortran code writes to stdout
            pe = subprocess.run(cmdlist, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            raise mesonlib.EnvironmentException(f'Could not invoke sanity test executable: {e!s}.')
        if pe.returncode != 0:
            raise mesonlib.EnvironmentException(f'Executables created by {self.language} compiler {self.name_string()} are not runnable.')
