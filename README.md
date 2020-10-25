# PIC32-ProgrammingProtocolDecoders
ICSP and JTAG decoders for sigrok/pulseview, for the PIC32 family of microcontrollers

These decoders were used when developing additional JTAG&ICSP support for FTDI probes in pic32prog (now [progyon](https://gitlab.com/spicastack/progyon)).

## JTAG

The JTAG decoder should be fairly complete. It was used to check what a combination of J-Link & MPLAB did in JTAG mode, if a microcontroller was "stuck". That happened (and still does) for MX1/2 parts, if they are flashed via JTAG - further JTAG flashing needs a power cycle, or poking the chip into ICSP and then back.

(Not much is the answer btw, there was no special handling or rescuing of the controller. The reset was probably done via the PE, which wasn't implemented in pic32prog)

## ICSP

The ICSP decoder was written first, and it shows.

The code is hardcoded to a specific number of cycles, which isn't great. Currently it's left as it was used last - for the Pickit 3. Pickit3 only does 32bits in a 33bit transaction (XferFastData), skipping one (the PrAcc bit).

TODO - remake to JTAG-level, with proper JTAG states, not just hardcoded cycles.