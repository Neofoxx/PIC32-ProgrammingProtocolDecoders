'''
Microchip ICSP decoder, with 4-phase supprt (2-phase is not supported)
Everything is CLOCK driven
-> First there needs to be a Reset, to get into a known state
-> Then there should be an entry pattern
-> Then we go on.

Update - now properly moves through all JTAG states (it's just JTAG over ICSP)
'''

import sigrokdecode as srd
import time

PIN_RESET, PIN_CLOCK, PIN_DATA = range(3)	# Pins, same as channels = (...)
MTAP, ETAP = range(2)	# TAPs in the microcontroller

MTAP_COMMAND = 0x07
MTAP_SW_MTAP = 0x04
MTAP_SW_ETAP = 0x05
E_MTAP_IDCODE = 0x01

ETAP_ADDRESS = 0x08
ETAP_DATA = 0x09
ETAP_CONTROL = 0x0A
ETAP_EJTAGBOOT = 0x0C
ETAP_FASTDATA = 0x0E

# MTAP_COMMAND DR commands
MTAP_DR_MCHP_STATUS = 0x00
MTAP_DR_MCHP_ASSERT_RST = 0xD1
MTAP_DR_MCHP_DE_ASSERT_RST = 0xD0
MTAP_DR_MCHP_ERASE = 0xFC
MTAP_DR_MCHP_FLASH_ENABLE = 0xFE
MTAP_DR_MCHP_FLASH_DISABLE = 0xFD

MTAP_INSTRUCTIONS = {MTAP_COMMAND:'MTAP_COMMAND', MTAP_SW_MTAP:'MTAP_SW_MTAP', MTAP_SW_ETAP:'MTAP_SW_ETAP', E_MTAP_IDCODE:'E_MTAP_IDCODE'}
ETAP_INSTRUCTIONS = {ETAP_ADDRESS:'ETAP_ADDRESS', ETAP_DATA:'ETAP_DATA', ETAP_CONTROL:'ETAP_CONTROL', ETAP_EJTAGBOOT:'ETAP_EJTAGBOOT', ETAP_FASTDATA:'ETAP_FASTDATA'}
INSTRUCTIONS = {MTAP_COMMAND:'MTAP_COMMAND', MTAP_SW_MTAP:'MTAP_SW_MTAP', MTAP_SW_ETAP:'MTAP_SW_ETAP', E_MTAP_IDCODE:'E_MTAP_IDCODE', ETAP_ADDRESS:'ETAP_ADDRESS', ETAP_DATA:'ETAP_DATA', ETAP_CONTROL:'ETAP_CONTROL', ETAP_EJTAGBOOT:'ETAP_EJTAGBOOT', ETAP_FASTDATA:'ETAP_FASTDATA'}

MTAP_COMMAND_DR = {MTAP_DR_MCHP_STATUS:'MTAP_DR_MCHP_STATUS', MTAP_DR_MCHP_ASSERT_RST:'MTAP_DR_MCHP_ASSERT_RST', MTAP_DR_MCHP_DE_ASSERT_RST:'MTAP_DR_MCHP_DE_ASSERT_RST', MTAP_DR_MCHP_ERASE:'MTAP_DR_MCHP_ERASE', MTAP_DR_MCHP_FLASH_ENABLE:'MTAP_DR_MCHP_FLASH_ENABLE', MTAP_DR_MCHP_FLASH_DISABLE:'MTAP_DR_MCHP_FLASH_DISABLE'}

# JTAG related stuff & states. Gotta do it properly, because J-Link
# JS == JtagState
JS_TestLogicReset, JS_RunTestIdle, JS_SelectDRScan, JS_CaptureDR, JS_ShiftDR, JS_Exit1DR, JS_PauseDR, JS_Exit2DR, JS_UpdateDR, JS_SelectIRScan, JS_CaptureIR, JS_ShiftIR, JS_Exit1IR, JS_PauseIR, JS_Exit2IR, JS_UpdateIR = range(16)
JSLookup = {JS_TestLogicReset:'TestLogicReset', JS_RunTestIdle:'RunTestIdle', JS_SelectDRScan: 'SelectDRScan', JS_CaptureDR:'CaptureDR', JS_ShiftDR:'ShiftDR', JS_Exit1DR:'Exit1DR', JS_PauseDR:'PauseDR', JS_Exit2DR:'Exit2DR', JS_UpdateDR:'UpdateDR', JS_SelectIRScan:'SelectIRScan', JS_CaptureIR:'CaptureIR', JS_ShiftIR:'ShiftIR', JS_Exit1IR:'Exit1IR', JS_PauseIR:'PauseIR', JS_Exit2IR:'Exit2IR', JS_UpdateIR:'UpdateIR'}



class Decoder(srd.Decoder):
	api_version = 3
	id = 'pic32_icsp'
	name = 'PIC32-ICSP'
	longname = 'Microchip PIC32 ICSP (4-phase)'
	desc = 'PIC32 programming protocol-'
	license = 'gplv2+'
	inputs = ['logic']
	outputs = ['pic32_icsp']
	channels = (
		{'id': 'reset', 'name': 'MCLR', 'desc': 'Reset line'},
		{'id': 'clock', 'name': 'PGEC', 'desc': 'Clock'},
		{'id': 'data', 'name': 'PGED', 'desc': 'Data'},	
	)
	annotations = (
		('sync', 'SYNC'),							# 0
		('enter-icsp', 'Entering ICSP'),			# 1
		('mtap-instruction', 'MTAP instrucion'),	# 2
		('etap-instruction', 'ETAP instrucion'),	# 3
		('mtap-dr-command', 'MTAP DR command'),		# 4
		('data', 'DATA'),							# 5
		('fast-data', 'Fast DATA'),					# 6
		('unknown', 'Unknown'),						# 7
		('jtag-state', 'JTAG state'),				# 8
		('tms', 'TMS data'),						# 9
		('tdi', 'TDI data'),						# 10
		('tdo', 'TDO data'),						# 11
		('tap-state-mtap', 'TAP state MTAP'),		# 12
		('tap-state-etap', 'TAP state ETAP'),		# 13
		('js-tlr', 'Test-Logic-Reset'),				# 14
		('js-rti', 'Run-Test-Idle'),				# 15
		('js-DR', 'Data-Register'),					# 16
		('js-IR', 'Instruction-Register'),			# 17

		
	)
	# Annotation_rows - the end numbers are a tuple, 
	#					where the above annotations go!
	annotation_rows = (
		('jtag-state', 'JS', (0, 1, 8, 14, 15, 16, 17, )),
		('tap-state', 'TAP', (12, 13, )),			
		('command', 'Command', tuple(range(2, 4+1))),
		('data', 'Data', tuple(range(5, 6+1))),
		('tms', 'TMS', (9, )),
		('tdi', 'TDI', (10, )),
		('tdo', 'TDO', (11, )),
		('unknown', 'WTF', (7, )),
	)


	def __init__(self):
		# Vars used 
		self.clockCycles = 0
		self.valueTDI = 0
		self.valueTDO = 0
		self.valueTMS = 0


	# Apparently now required?	
	def reset(self):
		self.onResetAsserted()
	
	def start(self):
		self.out_ann = self.register(srd.OUTPUT_ANN)
		self.stateJTAG = 0		# Assume TestLogicReset
		self.statePrevJTAG = 0
		self.selectedTAP = 0	# Assum MTAP
		self.clockCycles = 0	
		self.valueTDI = 0
		self.valueTDO = 0
		self.valueTMS = 0
		self.selectedRegister = 0;
		
		self.startSampleTLR = 0
		self.startSampleRTI = 0
		self.startSampleScan = 0
		self.startSampleCapture = 0
		self.startSampleShift = 0
		self.startSampleShiftData = 0
		self.startSampleExitOne = 0
		self.startSamplePause = 0
		self.startSampleExitTwo = 0
		self.startSampleUpdate = 0

		self.valueInReset = 0
	
		self.enteredICSP = 0
		
		
	def onResetAsserted(self):
		# We need this, because the "JTAG"/ICSP controller gets reset on RESET.
		self.valueInReset = 0
		self.clockCycles = 0	
		self.startSample = self.samplenum	# From where we will annotate
		self.enteredICSP = 0
		self.valueInReset = 0

	def onResetDeasserted(self):
		# We need this, because the "JTAG"/ICSP controller gets reset on RESET.
		if (self.clockCycles == 32 and self.valueInReset == 0x4D434850):	# If value was MCHP
			self.put(self.startSample, self.samplenum, self.out_ann, [1, ['ICSP ENTER']])
			self.enteredICSP = 1
		else:
			self.enteredICSP = -1	# Denote failure to enter

		self.valueTDI = 0
		self.valueTDO = 0
		self.valueTMS = 0
		self.clockCycles = 0	
		self.selectedTAP = 0;
		self.selectedRegister = 0;
		self.startSample = self.samplenum



	def decode(self):
		reset, clock, data = self.wait()	# Without arguments, we get the next sample (or first in this case) 
		
		# If reset already 0, then call onResetAsserted. Else first wait until it's 0, then call that.
		if (reset == 1):
			conds = []
			conds.append({PIN_RESET: 'f'})		# On falling reset
			reset, clock, data = self.wait(conds)	# Get pins
		self.onResetAsserted()
		
		while True:
			stringsToPrint = []		

			if (self.enteredICSP <= 0):

				# Loop here, until ICSP is entered.
				# We enter under reset == 0, so we
				conds = [] 
				conds.append({PIN_CLOCK: 'r'})		# On rising reset, or rising clock
				conds.append({PIN_RESET: 'r'})	
				reset, clock, data = self.wait(conds)	# Get pins
				
				if (reset == 1):
					# Check if all conditions have been met
					self.onResetDeasserted()
				else:
					# Check if last reset toggle was unsuccessful
					if (self.enteredICSP == -1):
						self.onResetAsserted()
						self.enteredICSP = 0
					# Clock high - save value into raw register
					# Shift right and ave into LSB, as data comes MSB first
					# Added precaution against infinite integers... Ask me why.
					self.valueInReset = ((self.valueInReset << 1) | data ) & 0xFFFFFFFF	
					self.clockCycles = self.clockCycles + 1
					if (self.clockCycles > 100):	# BS prevention.
						self.clockCycles = 100

			
			else:
				# After we are in ICSP, we just need to do JTAG over ICSP.
				# Which is just 4 CLK cycles per one bit.
				# First bit is on falling edge (PROG to TARGET) - TDI
				# Second bit is on falling edge (PROG to TARGET) - TMS
				# Third bit is dummy (role switchover) Can trigger on falling anyway
				# Fourth bit is on RISING edge (TARGET to PROG) - TDO
				# And that gives us our four bits.
				tdi = 0
				tms = 0
				tdo = 0
				
				conds = []
				conds.append({PIN_CLOCK: 'f'})					# On falling clock
				conds.append({PIN_RESET: 'f'})					# Or falling reset (there is a case for this) 
				# First bit, falling clock, TDI
				reset, clock, data = self.wait(conds)	# Get all bits
				tdi = data
				if (reset == 0):
					self.onResetAsserted()
					continue	
				# Second bit, falling clock, TMS				
				reset, clock, data = self.wait(conds)	# Get all bits
				tms = data
				if (reset == 0):
					self.onResetAsserted()
					continue	
				# Third bit, dummy, falling clock, discard
				reset, clock, data = self.wait(conds)	# Get all bits
				# Fourth bit, on RISING clock, TDO
				conds = []
				conds.append({PIN_CLOCK: 'r'})					# On rising clock
				conds.append({PIN_RESET: 'f'})					# Or falling reset (there is a case for this) 
				reset, clock, data = self.wait(conds)	# Get all bits
				tdo = data
				if (reset == 0):
					self.onResetAsserted()
					continue	
				# Fourth bit, on falling clock, cleanup - we have to finish the 4th CLK cycle
				conds = []
				conds.append({PIN_CLOCK: 'f'})					# On falling clock
				conds.append({PIN_RESET: 'f'})					# Or falling reset (there is a case for this) 
				reset, clock, data = self.wait(conds)	# Get all bits
				if (reset == 0):
					self.onResetAsserted()
					continue	
				
				# At this point we are done getting bits, and can proceed with decoding data and such.
				# Since it's kinda-sorta-but-not-really-still-yes JTAG over ICSP, here are the main components
				# (Notes for me):
				# SetMode, is just sending TMS until we end up in the right state (usualy Run-Test/Idle, but can differ). TDO is ignored, TDI should be 0.
				# SendCommand, 4 bits TMS, then (5-1) bits of data (first bit TDI is LSB), then 3 bits of TMS footer, with first bit also MSB of command
				# XferData, 3 bits TMS, with last bit also TDO = oLSb. Followed by (32-1) bits of data, first is TDI = iLSb, TDO = oLSb+1. Then 3 bits of TMS foorter, first is TDI = iMSb.
				# XferFastData, 3 bits TMS, with last bit also TDO = oPrAcc, then one bit of PrAcc, where TDI = _0_, TDO = oLSb.
				## Then (32-1) bits of data, where first is TDI = iLSb, TDO = oLSb+1
				## Then 3 bits of TMS footer, with first bt also TDI = iMSb. TDO was transmitted already fully before
				## XferFastData is equal to XferData, just with one extra bit. This bit is dropped by PicKit 3. That, and FastData register is selected ofc -> nice hook.
				### Tried checking Pickit 3 for the 32bit FastData transfers, and now they're ok? Might've been the decoder at fault or something.
				# XferInstruction is just XferData, with ETAP_DATA selected and then sending ETAP_CONTROL and 32 0s.
				
				# Anyways, nothing to fret. Eerything still gets checked in Update-DR or Update-IR.
				
				
				# First we check whhich state we are, and do that operation
				# afterwards, we check the TMS state, and move accordingly if needed			
				
				self.statePrevJTAG = self.stateJTAG	# Makes easier to update
				

				if (JS_TestLogicReset == self.stateJTAG):
					stringsToPrint.append([self.startSampleTLR, self.out_ann, [14, ['Test-Logic-Reset']]])
					self.selectedRegister = E_MTAP_IDCODE
					if (0 == tms):
						self.stateJTAG = JS_RunTestIdle
					# Else loop back to TLR
				elif (JS_RunTestIdle == self.stateJTAG):
					stringsToPrint.append([self.startSampleRTI, self.out_ann, [15, ['Run-Test-Idle']]])
					if (1 == tms):
						self.stateJTAG = JS_SelectDRScan
					# Else loop back to RTI
## Scan versions
				elif (JS_SelectDRScan == self.stateJTAG):
					stringsToPrint.append([self.startSampleScan, self.out_ann, [16, ['Select-DR-Scan']]])
					if (0 == tms):
						self.stateJTAG = JS_CaptureDR
					else:
						self.stateJTAG = JS_SelectIRScan

				elif (JS_SelectIRScan == self.stateJTAG):
					stringsToPrint.append([self.startSampleScan, self.out_ann, [17, ['Select-IR-Scan']]])
					if (0 == tms):
						self.stateJTAG = JS_CaptureIR
					else:
						self.stateJTAG = JS_TestLogicReset	# Loop back

## Capture versions
				elif (JS_CaptureDR == self.stateJTAG):
					stringsToPrint.append([self.startSampleCapture, self.out_ann, [16, ['Capture-DR']]])
					if (0 == tms):
						self.stateJTAG = JS_ShiftDR
						self.valueTDI = 0	## Prep variables
						self.valueTDO = tdo	# Expanded for ICSP. TDO oLSb or oPrAcc is read HERE. 
						self.valueTMS = 0
						self.clockCycles = 0
						self.startSampleShiftData = self.samplenum
					else:
						self.stateJTAG = JS_Exit1DR

				elif (JS_CaptureIR == self.stateJTAG):
					stringsToPrint.append([self.startSampleCapture, self.out_ann, [17, ['Capture-IR']]])
					if (0 == tms):
						self.stateJTAG = JS_ShiftIR
						self.valueTDI = 0	## Prep variables
						self.valueTDO = 0
						self.valueTMS = 0
						self.clockCycles = 0
						self.startSampleShiftData = self.samplenum
					else:
						self.stateJTAG = JS_Exit1IR
## Shift versions
				elif (JS_ShiftDR == self.stateJTAG):
					## SHIFT DATA IN!!!! LSB first ><
					self.valueTDI = self.valueTDI | (tdi<<self.clockCycles)
					self.valueTDO = self.valueTDO | (tdo<<self.clockCycles)
					self.valueTMS = self.valueTMS | (tms<<self.clockCycles)
					self.clockCycles = self.clockCycles + 1
					stringsToPrint.append([self.startSampleShift, self.out_ann, [16, ['Shift-DR']]])
					if (1 == tms):
						self.stateJTAG = JS_Exit1DR
						# Expanded for ICSP. On a Shift-DR -> Exit1-DR transition, TDO is discarded.
						self.valueTDO = self.valueTDO ^ (tdo<<(self.clockCycles-1))	# XOR the bit, if set

				elif (JS_ShiftIR == self.stateJTAG):
					## SHIFT DATA IN!!!! LSB first ><
					self.valueTDI = self.valueTDI | (tdi<<self.clockCycles)
					self.valueTDO = self.valueTDO | (tdo<<self.clockCycles)
					self.valueTMS = self.valueTMS | (tms<<self.clockCycles)
					self.clockCycles = self.clockCycles + 1
					stringsToPrint.append([self.startSampleShift, self.out_ann, [17, ['Shift-IR']]])
					if (1 == tms):
						self.stateJTAG = JS_Exit1IR
					
## Exit versions
				elif (JS_Exit1DR == self.stateJTAG):
					stringsToPrint.append([self.startSampleExit, self.out_ann, [16, ['Exit1-DR']]])
					if (0 == tms):
						self.stateJTAG = JS_PauseDR
					else:
						self.stateJTAG = JS_UpdateDR

				elif (JS_Exit1IR == self.stateJTAG):
					stringsToPrint.append([self.startSampleExit, self.out_ann, [17, ['Exit1-IR']]])
					if (0 == tms):
						self.stateJTAG = JS_PauseIR
					else:
						self.stateJTAG = JS_UpdateIR

## Pause versions
				elif (JS_PauseDR == self.stateJTAG):
					stringsToPrint.append([self.startSamplePause, self.out_ann, [16, ['Pause-DR']]])
					if (1 == tms):
						self.stateJTAG = JS_Exit2DR
				elif (JS_PauseIR == self.stateJTAG):
					stringsToPrint.append([self.startSamplePause, self.out_ann, [17, ['Pause-IR']]])
					if (1 == tms):
						self.stateJTAG = JS_Exit2IR
					
## Exit versions
				elif (JS_Exit2DR == self.stateJTAG):
					stringsToPrint.append([self.startSampleExit, self.out_ann, [16, ['Exit2-DR']]])
					if (0 == tms):
						self.stateJTAG = JS_ShiftDR
					else:
						self.stateJTAG = JS_UpdateDR
				elif (JS_Exit2IR == self.stateJTAG):
					stringsToPrint.append([self.startSampleExit, self.out_ann, [17, ['Exit2-IR']]])
					if (0 == tms):
						self.stateJTAG = JS_ShiftIR
					else:
						self.stateJTAG = JS_UpdateIR
					

## Update versions, the fun stuff
				elif (JS_UpdateDR == self.stateJTAG):
					stringsToPrint.append([self.startSampleUpdate, self.out_ann, [16, ['Update-DR']]])
					stringsToPrint.append([self.startSampleShiftData, self.out_ann, [9, ['TMS ' + str(self.clockCycles) + 'b ' + str(hex(self.valueTMS))]]])
					stringsToPrint.append([self.startSampleShiftData, self.out_ann, [10, ['TDI ' + str(self.clockCycles) + 'b ' + str(hex(self.valueTDI))]]])
					stringsToPrint.append([self.startSampleShiftData, self.out_ann, [11, ['TDO ' + str(self.clockCycles) + 'b ' + str(hex(self.valueTDO))]]])

### Decoding
					if (self.clockCycles == 5):
						# Ok, this is a 5bit instruction
						if (self.valueTDI not in INSTRUCTIONS):
							stringsToPrint.append([self.startSampleShiftData, self.out_ann, [2, ['Unknown command: ' + str(hex(self.valueTDI))]]])					
						else:
							if (self.selectedTAP == ETAP):
								stringsToPrint.append([self.startSampleShiftData, self.out_ann, [3, ['ETAP COMMAND: ' + INSTRUCTIONS[self.valueTDI]]]])
							else:
								stringsToPrint.append([self.startSampleShiftData, self.out_ann, [2, ['MTAP COMMAND: ' + INSTRUCTIONS[self.valueTDI]]]])
							if (self.valueTDI == MTAP_SW_ETAP):
								self.selectedTAP = ETAP
							elif(self.valueTDI == MTAP_SW_MTAP):
								self.selectedTAP = MTAP
		
							self.selectedRegister = self.valueTDI	# Save selected register
						
					
					elif (self.selectedRegister == MTAP_COMMAND):
						# Ok, this is an 8-bit Command DR thing (should be in the upper quadrant)
						if (self.valueTDI in MTAP_COMMAND_DR):
							stringsToPrint.append([self.startSampleShiftData, self.out_ann, [4, ['COMMAND_DR: ' + MTAP_COMMAND_DR[self.valueTDI]]]])	
						else:
							stringsToPrint.append([self.startSampleShiftData, self.out_ann, [4, ['COMMAND_DR: Unknown :( ' + str(hex(self.valueTDI))]]])
					elif (self.clockCycles == 32):
						# Just normal data
						stringsToPrint.append([self.startSampleShiftData, self.out_ann, [5, ['Normal data transfer TDI: ' +  str(hex(self.valueTDI))  + ' TDO: ' + str(hex(self.valueTDO)) ]]])
					elif (self.selectedRegister == ETAP_FASTDATA):	# Could check for 33 bits -> NO! Pickit frigs this up.
						# FAST DATA
						# TODO, CHECK this and improve for pickit (><)
						## >>1 are there to remove bits from PrAcc. Needs to be revised
						if (self.clockCycles == 32):
							# Pickit transfer
							stringsToPrint.append([self.startSampleShiftData, self.out_ann,\
							[5, ['Fast data transfer TDI: ' +  str(hex(self.valueTDI>>1))  + ' TDO: ' + str(hex(self.valueTDO>>1))\
							+ ' PrAcc PIC: ' + str(hex(self.valueTDO & 0x01)) + ' PrAcc PROBE: ' + str(hex(self.valueTDI & 0x01))  ]]])	# PrAcc PROBE is probably missing on Pickit.
						else:
							# Either normal fast transfer, or error.
							stringsToPrint.append([self.startSampleShiftData, self.out_ann,\
							[5, ['Fast data transfer TDI: ' +  str(hex(self.valueTDI>>1))  + ' TDO: ' + str(hex(self.valueTDO>>1))\
							+ ' PrAcc PIC: ' + str(hex(self.valueTDO & 0x01)) + ' PrAcc PROBE: ' + str(hex(self.valueTDI & 0x01))  ]]])	
### End decoding
					
					if (0 == tms):
						self.stateJTAG = JS_RunTestIdle
					else:
						self.stateJTAG = JS_SelectDRScan
				elif (JS_UpdateIR == self.stateJTAG):
					stringsToPrint.append([self.startSampleUpdate, self.out_ann, [17, ['Update-IR']]])
					stringsToPrint.append([self.startSampleShiftData, self.out_ann, [9, ['TMS ' + str(self.clockCycles) + 'b ' + str(hex(self.valueTMS))]]])
					stringsToPrint.append([self.startSampleShiftData, self.out_ann, [10, ['TDI ' + str(self.clockCycles) + 'b ' + str(hex(self.valueTDI))]]])
					stringsToPrint.append([self.startSampleShiftData, self.out_ann, [11, ['TDO ' + str(self.clockCycles) + 'b ' + str(hex(self.valueTDO))]]])

### Decoding
					if (self.clockCycles == 5):
						# Ok, this is a 5bit instruction
						if (self.valueTDI not in INSTRUCTIONS):
							stringsToPrint.append([self.startSampleShiftData, self.out_ann, [2, ['Unknown command: ' + str(hex(self.valueTDI))]]])					
						else:
							if (self.selectedTAP == ETAP):
								stringsToPrint.append([self.startSampleShiftData, self.out_ann, [3, ['ETAP COMMAND: ' + INSTRUCTIONS[self.valueTDI]]]])
							else:
								stringsToPrint.append([self.startSampleShiftData, self.out_ann, [2, ['MTAP COMMAND: ' + INSTRUCTIONS[self.valueTDI]]]])
							if (self.valueTDI == MTAP_SW_ETAP):
								self.selectedTAP = ETAP
							elif(self.valueTDI == MTAP_SW_MTAP):
								self.selectedTAP = MTAP
		
							self.selectedRegister = self.valueTDI	# Save selected register
						
					
					elif (self.selectedRegister == MTAP_COMMAND):
						# Ok, this is an 8-bit Command DR thing (should be in the upper quadrant)
						if (self.valueTDI in MTAP_COMMAND_DR):
							stringsToPrint.append([self.startSampleShiftData, self.out_ann, [4, ['COMMAND_DR: ' + MTAP_COMMAND_DR[self.valueTDI]]]])	
						else:
							stringsToPrint.append([self.startSampleShiftData, self.out_ann, [4, ['COMMAND_DR: Unknown :( ' + str(hex(self.valueTDI))]]])
					elif (self.clockCycles == 32):
						# Just normal data
						stringsToPrint.append([self.startSampleShiftData, self.out_ann, [5, ['Normal data transfer']]])
					elif (self.selectedRegister == ETAP_FASTDATA):	# Could check for 33 bits
						# FAST DATA
						stringsToPrint.append([self.startSampleShiftData, self.out_ann, [5, ['Fast data transfer TDI:' +  str(hex(self.valueTDI>>1))  + ' TDO: ' + str(hex(self.valueTDO>>1)) ]]])
### End decoding

					if (0 == tms):
						self.stateJTAG = JS_RunTestIdle
					else:
						self.stateJTAG = JS_SelectDRScan

## Else, apocalypse
				else:
					print("Unknown State")
					while(1):
						continue



				# Also trigger on the FALLING edge, to make nicer ouput (center the bit on the rising edge)
				# Reverse archeology is fun...
				# So, our stringsToPrint were [start position], [out annotation?], [actual data to print]
				# Here, so do some muckery, to align it bit perfect etc.
				# Can't do that, so modify.
				#conds = []
				#conds.append({PIN_CLOCK: 'f'})
				#reset, tms, tck, tdi, tdo = self.wait(conds)
				#for x in stringsToPrint:
				#	self.put(x[0], self.samplenum, x[1], x[2])
				for x in stringsToPrint:
					self.put(x[0], self.samplenum, x[1], x[2])
					

				# Code duplication. Meh
				if (JS_TestLogicReset == self.stateJTAG):
					self.startSampleTLR = self.samplenum
				elif (JS_RunTestIdle == self.stateJTAG):
					self.startSampleRTI = self.samplenum
				elif (JS_SelectDRScan == self.stateJTAG or JS_SelectIRScan == self.stateJTAG):
					self.startSampleScan = self.samplenum
				elif (JS_CaptureDR == self.stateJTAG or JS_CaptureIR == self.stateJTAG):
					self.startSampleCapture = self.samplenum
				elif (JS_ShiftDR == self.stateJTAG or JS_ShiftIR == self.stateJTAG):
					self.startSampleShift = self.samplenum
				elif (JS_Exit1DR == self.stateJTAG or JS_Exit1IR == self.stateJTAG or JS_Exit2DR == self.stateJTAG or JS_Exit2IR == self.stateJTAG):
					self.startSampleExit = self.samplenum
				elif (JS_PauseDR == self.stateJTAG or JS_PauseIR == self.stateJTAG):
					self.startSamplePause = self.samplenum
				elif (JS_UpdateDR == self.stateJTAG or JS_UpdateIR == self.stateJTAG):
					self.startSampleUpdate = self.samplenum

###############################################################################
	
