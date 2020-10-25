'''
Microchip ICSP protocol decoder

The protocol uses two lines - CLK and DATA, similar to SWD.
It multiplexes JTAG pins (TDI, TMS, x, TDO) in 4 clock cycles (4-phase).
Only 4-phase ICSP is supported, 2-phase is not.

'''

from .pd import Decoder
