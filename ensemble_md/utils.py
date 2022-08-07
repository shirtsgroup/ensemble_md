####################################################################
#                                                                  #
#    ensemble_md,                                                  #
#    a python package for running GROMACS simulation ensembles     #
#                                                                  #
#    Written by Wei-Tse Hsu <wehs7661@colorado.edu>                #
#    Copyright (c) 2022 University of Colorado Boulder             #
#                                                                  #
####################################################################
"""
The `utils` module provides useful utility functions.
"""
import os
import sys
import natsort
import numpy as np


class Logger:
    """
    This redirect the STDOUT to a specified output file while preserving STDOUT on screen.
    """

    def __init__(self, logfile):
        self.terminal = sys.stdout
        self.log = open(logfile, "a")

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)

    def flush(self):
        # this flush method is needed for python 3 compatibility.
        # this handles the flush command by doing nothing.
        # you might want to specify some extra behavior here.
        # self.terminal.log()
        pass


def gmx_output(gmx_obj, verbose=False):
    """
    Tells if a command launched by ``gmxapi.commandline_operation`` failed or not.
    If the command failed, the function will print out STDOUT and STDERR of the process.

    Parameters
    ----------
    gmx_obj : obj
        An object generated by gmx.commandline_operation.
    verbose : bool
        If details should be printed.
    """
    try:
        rtn_code = gmx_obj.output.returncode.result()
        if type(rtn_code) == list:  # simulation ensemble
            if sum(rtn_code) == 0:
                if verbose is True:
                    print("The process was executed successfully.")
            else:
                print(f"Return codes: {rtn_code}")
                for i in range(len(rtn_code)):
                    if rtn_code[i] != 0:
                        print(
                            f"STDERR of the process:\n\n {gmx_obj.output.stderr.result()[i]}\n"
                        )
        else:  # single simulation
            if rtn_code == 0:
                if verbose is True:
                    print("The process was executed successfully.")
            else:
                print(f"STDERR of the process:\n\n {gmx_obj.output.stderr.result()}\n")
    except AttributeError:
        raise RuntimeError(f"{repr(gmx_obj)} is not a commandline_operation.")


def clean_up(dir_before, dir_after, verbose=False):
    """
    Removes newly generated folders that are empty after a command launched by gmxapi.

    Parameters
    ----------
    dir_before : list
        The list of directories existed before the command was executed.
    dir_after : list
        The list of directories existed after the command was executed. This helps
        figure out which directories are newly generated by command.
    verbose : bool
        If details should be printed.
    """
    new_dirs = natsort.natsorted([i for i in dir_after if i not in dir_before])
    if len(new_dirs) != 0:
        if verbose is True:
            print("\nCleaning up/restructuring the directories ...")
    for i in new_dirs:
        if len(os.listdir(i)) == 0:
            if verbose is True:
                print(f"  Removing the empty folder {i} ...")
            os.rmdir(i)


def format_time(t):
    """
    This function convert time in seconds to the "most readable" format.
    """
    import datetime

    hh_mm_ss = str(datetime.timedelta(seconds=t)).split(":")
    hh, mm, ss = float(hh_mm_ss[0]), float(hh_mm_ss[1]), float(hh_mm_ss[2])
    if hh == 0:
        if mm == 0:
            t_str = f"{ss:.1f} second(s)"
        else:
            t_str = f"{mm:.0f} minute(s) {ss:.0f} second(s)"
    else:
        t_str = f"{hh:.0f} hour(s) {mm:.0f} minute(s) {ss:.0f} second(s)"

    return t_str


def autoconvert(s):
    """Convert input to a numerical type if possible. Used for the MDP parser.
    Modified from `utilities.py in GromacsWrapper <https://github.com/Becksteinlab/GromacsWrapper>`_.
    Copyright (c) 2009 Oliver Beckstein <orbeckst@gmail.com>

      - A non-string object is returned as it is
      - Try conversion to int, float, str.
    """
    if type(s) is not str:
        return s
    for converter in int, float, str:  # try them in increasing order of lenience
        try:
            s = [converter(i) for i in s.split()]
            if len(s) == 1:
                return s[0]
            else:
                return np.array(s)
        except (ValueError, AttributeError):
            pass
    raise ValueError("Failed to autoconvert {0!r}".format(s))
