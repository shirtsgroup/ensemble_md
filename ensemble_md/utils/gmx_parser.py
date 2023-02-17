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
The :code:`gmx_parser` module provides functions for parsing GROMACS files.
"""
import os
import re
import six
import logging
import warnings
from collections import OrderedDict as odict

from ensemble_md.utils import utils
from ensemble_md.utils.exceptions import ParseError


def parse_log(log_file):
    """
    This function parses a log file generated by expanded ensemble and provide
    important information especially for running new iterations in EEXE.
    Typically, there are three types of log files from an expanded ensemble simulation:

    - Case 1: The weights are equilibrating in the simulation but the equilibration was not done.
      - :code:`equil_time` should always be -1.
    - Case 2: The weights were equilibrated during the simulation.
      - :code:`equil_time` should be the time (ps) that the weights get equilibrated.
      - The final weights will just be the equilibrated weights.
    - Case 3: The weights were fixed in the simulation.
      - :code:`equil_time` should always be 0.
      - We can still find the final weights (not changed though) and the final counts.

    Parameters
    ----------
    log_file : str
        The log file to be parsed.

    Returns
    -------
    wl_delta : float
        The final Wang-Landau incementor
    weights : list
        The final list of lambda weights.
    counts : list
        The final histogram counts.
    equil_time : int or float
        The time in ps that the weights get equilibrated.
        -1 means that the weights have not been equilibrated (Case 1).
        0 means that the weights were fixed during the simulation (Case 3).
    """
    f = open(log_file, "r")
    lines = f.readlines()
    f.close()

    wl_delta_found, weights_found = False, False
    weights, counts = [], []
    case_1_3, equil_time_found = False, False

    for l in lines:  # noqa: E741
        if "n-lambdas" in l:
            N_states = int(l.split("=")[1])
        if "tinit" in l:
            tinit = float(l.split("=")[1])
        if "lmc-stats" in l:
            if l.split("=")[1].split()[0] in ["no", "No"]:
                # Case 3: The weights are fixed. -> Typically weights have been equilibrated in the previous iteration.
                fixed_bool = True
                equil_time = 0
                wl_delta = None
                wl_delta_found = True
                case_1_3 = True
            else:
                # Either Case 1 or Case 2
                fixed_bool = False
                equil_time = -1
        if "dt  " in l:
            dt = float(l.split("=")[1])

    lines.reverse()  # We find the information from the end
    n = -1
    for l in lines:  # noqa: E741
        n += 1
        if wl_delta_found is False:  # Case 1 or Case 2
            if "Wang-Landau incrementor is" in l:
                wl_delta_found = True
                wl_delta = float(l.split(":")[1])

        if weights_found is False:
            if "Count   G(in kT)" in l:
                weights_found = True  # The first occurrence would be the final weights. (We've reversed the lines!)
                for i in range(1, N_states + 1):
                    if "<<" in lines[n - i]:
                        weights.append(float(lines[n - i].split()[-3]))
                        counts.append(int(lines[n - i].split()[-4]))
                    else:
                        weights.append(float(lines[n - i].split()[-2]))
                        counts.append(int(lines[n - i].split()[-3]))
                if "Wang-Landau incrementor is" in lines[n + 1]:  # Caes 1
                    equil_time = -1
                    wl_delta_found = True
                    wl_delta = float(lines[n + 1].split(":")[1])
                    case_1_3 = True
                else:
                    # This would include Case 2 and 3
                    if fixed_bool is True:
                        case_1_3 = True
                    else:
                        case_1_3 = False

        if case_1_3 is False:  # for finding when the weights were equilibrated in Case 2
            if "Weights have equilibrated" in l:
                equil_time_found = True
                equil_step = int(l.split(":")[0].split("Step")[1])
                equil_time = equil_step * dt + tinit  # ps

        # For Case 1 and Case 3 (case_1_3 = True), we can break the loop after getting weights, counts, and wl_delta.
        if case_1_3 is True and weights_found is True and wl_delta_found is True:
            break

        # For Case 2, we can break the loop only if equil_time is found as well.
        if (
            case_1_3 is False
            and weights_found is True
            and wl_delta_found is True
            and equil_time_found is True
        ):
            break

    return wl_delta, weights, counts, equil_time


class FileUtils(object):
    """Mixin class to provide additional file-related capabilities.
    Modified from `utilities.py in GromacsWrapper <https://github.com/Becksteinlab/GromacsWrapper>`_.
    Copyright (c) 2009 Oliver Beckstein <orbeckst@gmail.com>
    """

    #: Default extension for files read/written by this class.
    default_extension = None

    def _init_filename(self, filename=None, ext=None):
        """Initialize the current filename :attr:`FileUtils.real_filename` of the object.

        Bit of a hack.

        - The first invocation must have ``filename != None``; this will set a
          default filename with suffix :attr:`FileUtils.default_extension`
          unless another one was supplied.

        - Subsequent invocations either change the filename accordingly or
          ensure that the default filename is set with the proper suffix.

        """

        extension = ext or self.default_extension
        filename = self.filename(
            filename, ext=extension, use_my_ext=True, set_default=True
        )
        #: Current full path of the object for reading and writing I/O.
        self.real_filename = os.path.realpath(filename)

    def filename(self, filename=None, ext=None, set_default=False, use_my_ext=False):
        """Supply a file name for the class object.

        Typical uses::

           fn = filename()             ---> <default_filename>
           fn = filename('name.ext')   ---> 'name'
           fn = filename(ext='pickle') ---> <default_filename>'.pickle'
           fn = filename('name.inp','pdf') --> 'name.pdf'
           fn = filename('foo.pdf',ext='png',use_my_ext=True) --> 'foo.pdf'

        The returned filename is stripped of the extension
        (``use_my_ext=False``) and if provided, another extension is
        appended. Chooses a default if no filename is given.

        Raises a ``ValueError`` exception if no default file name is known.

        If ``set_default=True`` then the default filename is also set.

        ``use_my_ext=True`` lets the suffix of a provided filename take
        priority over a default ``ext`` tension.
        """
        if filename is None:
            if not hasattr(self, "_filename"):
                self._filename = None  # add attribute to class
            if self._filename:
                filename = self._filename
            else:
                raise ValueError(
                    "A file name is required because no default file name was defined."
                )
            my_ext = None
        else:
            filename, my_ext = os.path.splitext(filename)
            if set_default:  # replaces existing default file name
                self._filename = filename
        if my_ext and use_my_ext:
            ext = my_ext
        if ext is not None:
            if ext.startswith(os.extsep):
                ext = ext[1:]  # strip a dot to avoid annoying mistakes
            if ext != "":
                filename = filename + os.extsep + ext
        return filename


class MDP(odict, FileUtils):
    """Class that represents a Gromacs mdp run input file.
    Modified from `GromacsWrapper <https://github.com/Becksteinlab/GromacsWrapper>`_.
    Copyright (c) 2009-2011 Oliver Beckstein <orbeckst@gmail.com>
    The MDP instance is an ordered dictionary.

      - *Parameter names* are keys in the dictionary.
      - *Comments* are sequentially numbered with keys Comment0001,
        Comment0002, ...
      - *Empty lines* are similarly preserved as Blank0001, ....

    When writing, the dictionary is dumped in the recorded order to a
    file. Inserting keys at a specific position is not possible.

    Currently, comments after a parameter on the same line are
    discarded. Leading and trailing spaces are always stripped.
    """

    default_extension = "mdp"
    logger = logging.getLogger("gromacs.formats.MDP")

    COMMENT = re.compile("""\s*;\s*(?P<value>.*)""")  # eat initial ws  # noqa: W605
    # see regex in cbook.edit_mdp()
    PARAMETER = re.compile(
        """
                            \s*(?P<parameter>[^=]+?)\s*=\s*  # parameter (ws-stripped), before '='  # noqa: W605
                            (?P<value>[^;]*)                # value (stop before comment=;)  # noqa: W605
                            (?P<comment>\s*;.*)?            # optional comment  # noqa: W605
                            """,
        re.VERBOSE,
    )

    def __init__(self, filename=None, autoconvert=True, **kwargs):
        """Initialize mdp structure.

        :Arguments:
          *filename*
              read from mdp file
          *autoconvert* : boolean
              ``True`` converts numerical values to python numerical types;
              ``False`` keeps everything as strings [``True``]
          *kwargs*
              Populate the MDP with key=value pairs. (NO SANITY CHECKS; and also
              does not work for keys that are not legal python variable names such
              as anything that includes a minus '-' sign or starts with a number).
        """
        super(MDP, self).__init__(
            **kwargs
        )  # can use kwargs to set dict! (but no sanity checks!)

        self.autoconvert = autoconvert

        if filename is not None:
            self._init_filename(filename)
            self.read(filename)

    def __eq__(self, other):
        """
        __eq__ inherited from FileUtils needs to be overridden if new attributes (autoconvert in
        this case) are assigned to the instance of the subclass (MDP in our case).
        See `this post by LGTM <https://lgtm.com/rules/9990086/>`_ for more details.
        """
        if not isinstance(other, MDP):
            return False
        return FileUtils.__eq__(self, other) and self.autoconvert == other.autoconvert

    def _transform(self, value):
        if self.autoconvert:
            return utils.autoconvert(value)
        else:
            return value.rstrip()

    def read(self, filename=None):
        """Read and parse mdp file *filename*."""
        self._init_filename(filename)

        def BLANK(i):
            return "B{0:04d}".format(i)

        def COMMENT(i):
            return "C{0:04d}".format(i)

        data = odict()
        iblank = icomment = 0
        with open(self.real_filename) as mdp:
            for line in mdp:
                line = line.strip()
                if len(line) == 0:
                    iblank += 1
                    data[BLANK(iblank)] = ""
                    continue
                m = self.COMMENT.match(line)
                if m:
                    icomment += 1
                    data[COMMENT(icomment)] = m.group("value")
                    continue
                # parameter
                m = self.PARAMETER.match(line)
                if m:
                    # check for comments after parameter?? -- currently discarded
                    parameter = m.group("parameter")
                    value = self._transform(m.group("value"))
                    data[parameter] = value
                else:
                    errmsg = "{filename!r}: unknown line in mdp file, {line!r}".format(
                        **vars()
                    )
                    self.logger.error(errmsg)
                    raise ParseError(errmsg)

        super(MDP, self).update(data)

    def write(self, filename=None, skipempty=False):
        """Write mdp file to *filename*.

        Parameters
        ----------
        filename : str
            Output mdp file; default is the filename the mdp was read from. If the filename
            is not supplied, the function will overwrite the file that the mdp was read from.
        skipempty : bool
            ``True`` removes any parameter lines from output that contain empty values [``False``]
        """
        # The line 'if skipempty and (v == "" or v is None):' below could possibly incur FutureWarning
        warnings.simplefilter(action='ignore', category=FutureWarning)

        with open(self.filename(filename, ext="mdp"), "w") as mdp:
            for k, v in self.items():
                if k[0] == "B":  # blank line
                    mdp.write("\n")
                elif k[0] == "C":  # comment
                    mdp.write("; {v!s}\n".format(**vars()))
                else:  # parameter = value
                    if skipempty and (v == "" or v is None):
                        continue
                    if isinstance(v, six.string_types) or not hasattr(v, "__iter__"):
                        mdp.write("{k!s} = {v!s}\n".format(**vars()))
                    else:
                        mdp.write("{} = {}\n".format(k, " ".join(map(str, v))))
