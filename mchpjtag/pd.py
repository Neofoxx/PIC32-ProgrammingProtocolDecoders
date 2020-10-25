'''
Microchip JATG decoder, with optional J-Link support
Everything is CLOCK driven
-> It's not necessary, to have a reset!!! Could be, could be not. 
--> Do _not_ rely on reset, as J-Link doesn't use it, like at all.
'''

import sigrokdecode as srd
import time

PIN_RESET, PIN_TMS, PIN_CLOCK, PIN_TDI, PIN_TDO = range(5)	# Pins
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
	id = 'mchpjtag'
	name = 'MCHP_JTAG'
	longname = 'Microchip PIC32 JTAG'
	desc = 'PIC32 programming protocol-'
	license = 'gplv2+'
	inputs = ['logic']
	outputs = ['mchpjtag']
	channels = (
		{'id': 'reset', 'name': 'SYSRST', 'desc': 'Reset line'},
		{'id': 'tms', 'name': 'TMS', 'desc': 'Test Mode Select'},
		{'id': 'tck', 'name': 'TCK', 'desc': 'Clock'},
		{'id': 'tdi', 'name': 'TDI', 'desc': 'Data from programmer'},	
		{'id': 'tdo', 'name': 'TDO', 'desc': 'Data to programmer'},	
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

	def start(self):
		self.out_ann = self.register(srd.OUTPUT_ANN)
		self.stateJTAG = 0		# Assume TestLogicReset
		self.statePrevJTAG = 0
		self.selectedTAP = 0	# Assum MTAP
		self.clockCycles = 0	# 0 cycles at beginning
		self.valueTDI = 0
		self.valueTDO = 0
		self.valueTMS = 0
		self.selectedRegister = 0	# Selected register for MCHP decoding specifics	
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

	def varResetOnX(self):
		pass

	def decode(self):
		print("HERE 2");
		
		while True:
			#time.sleep(0.01)
			conds = []
			stringsToPrint = []
			
			# EVERYTHING is rising edge driven.
			conds.append({PIN_CLOCK: 'r'})	
			reset, tms, tck, tdi, tdo = self.wait(conds)

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
					self.valueTDO = 0
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
					stringsToPrint.append([self.startSampleShiftData, self.out_ann, [5, ['Normal data transfer']]])
				elif (self.selectedRegister == ETAP_FASTDATA):	# Could check for 33 bits
					# FAST DATA
					stringsToPrint.append([self.startSampleShiftData, self.out_ann, [5, ['Fast data transfer TDI:' +  str(hex(self.valueTDI>>1))  + ' TDO: ' + str(hex(self.valueTDO>>1)) ]]])
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
			conds = []
			conds.append({PIN_CLOCK: 'f'})
			reset, tms, tck, tdi, tdo = self.wait(conds)
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

'''
			print("STATE IS: " + str(self.state))
			if (self.state == STATE_PRE_RESET):
				# RESET asserted
				conds.append({PIN_RESET: 'f'})	# On falling edge
				
				self.state = STATE_RESET
				self.put(self.startSample, self.samplenum, self.out_ann, [7, ['Dunno']])
				self.onResetAsserted()
				continue

			elif (self.state == STATE_RESET):
				print("Here 4")
				conds.append({PIN_RESET: 'r'})
				conds.append({PIN_CLOCK: 'r'})	# On rising edge of clock, latch value. On rising edge of reset, go to next state
				reset, clock, data = self.wait(conds)
				print("HEre 5, " + str(reset) + " " + str(clock) + " " + str(data));
				print("Current vals: " + str(self.value) + " CC: " + str(self.clockCycles)) 
				if (reset == 0 and clock == 1):
					print("Hello?")
					if (self.clockCycles == 0):
						self.startSample = self.samplenum
					self.value = (self.value << 1) + data
					self.clockCycles =  self.clockCycles + 1
					
				if (reset == 1):
					print("Here 3")
					if (self.enteredICSP == 0):
						if (self.clockCycles == 32 and self.value == 0x4D434850):					
							self.state = STATE_POST_RESET
							self.onResetDeasserted()
							self.enteredICSP = 1
							continue
					else:
						self.onResetDeasserted()
						self.startSample = self.samplenum
						self.state = STATE_POST_RESET
					
				if (self.clockCycles == 32 and self.value == 0x4D434850):	# If value was MCHP
					self.put(self.startSample, self.samplenum, self.out_ann, [1, ['ICSP ENTER']])
					self.startSample = self.samplenum

				
				

				# Value is shifted MSB first!
				
				
			elif (self.state > STATE_RESET):
				
				if (self.subClockCycles == 3):	# Trigger on rising on fourth edge, else falling
					conds.append({ PIN_CLOCK: 'r'})
				else:
					conds.append({ PIN_CLOCK: 'f'})
				conds.append({PIN_RESET: 'f'})	# Handle rouge resets.
				
				reset, clock, data = self.wait(conds)
				print("Hi from 12, " + str(reset) + " " + str(clock) + " " + str(data))
					
				if (reset == 0):
					self.state = STATE_RESET
					self.onResetAsserted()
					self.startSample = self.samplenum
					continue

				## Quick fix for display alignment
				if (self.clockCycles == 0 and self.subClockCycles == 0):
					self.startSample = self.samplenum

				if (self.subClockCycles == 0):
					# Data is fed LSB ><
					if (data):
						self.valueTDI = self.valueTDI | (1<<self.clockCycles)
					self.subClockCycles = self.subClockCycles + 1

				elif (self.subClockCycles == 1):
					self.valueTMS = (self.valueTMS << 1) + data
					self.subClockCycles = self.subClockCycles + 1

				elif (self.subClockCycles == 2):
					self.subClockCycles = self.subClockCycles + 1

				elif (self.subClockCycles == 3):
					# Data is fed LSB ><
					if (data):
						self.valueTDO = self.valueTDO | (1<<self.clockCycles)
					self.subClockCycles = self.subClockCycles + 1

				elif (self.subClockCycles == 4):
					# After the last clock edge					
					self.subClockCycles = 0
					self.clockCycles = self.clockCycles + 1


					
					print("TMS value: " + str(self.valueTMS) + " ClockCycles: " + str(self.clockCycles))
					if (self.clockCycles > 4):
						self.valueTMSstart = (self.valueTMS >> (self.clockCycles - 4))	# Get TMS value at the beginning
						self.valueTMSstop = self.valueTMS & 0x07						# Get TMS value at the end
						print("TMS stop value: " + str(self.valueTMSstop) + " Start value: " + str(self.valueTMSstart))

						if (self.valueTMSstop == 0x06 and self.clockCycles > 4):		# End of command/instruciton/reset...
							if ((self.valueTMS & 0x3F) == 0x3E):						# Check for TAP reset (6b'111110), done on raw variable
								# This was a TAP reset packet. Select default command (IDCODE), in whichever TAP we are
								self.put(self.startSample, self.samplenum, self.out_ann, [8, ['TAP reset']])
								self.selectedRegister = E_MTAP_IDCODE
								self.onResetDeasserted()	
					
							elif(self.valueTMSstart == 	0x0C):
								# If TMS value is 4b'1100, then it's a command
								print("Got outselves a command!")
								print("Raw TDI value is " + str(self.valueTDI))
								print("Number of clocks at this point " + str(self.clockCycles))
								tempValueSent = self.valueTDI >> 4 # Cut off TMS HEADER. Damn LSBs
								tempValueSent = tempValueSent & ((2**((self.clockCycles - 2 - 4))) - 1 )	# -2 for cut off footer, -4 for command header
								print("Command probably: " + str(tempValueSent))
								
								if (tempValueSent not in INSTRUCTIONS):
									self.put(self.startSample, self.samplenum, self.out_ann, [7, ['Unknown command: ' + str(hex(tempValueSent))]])								
								else:
									if (self.selectedTAP == ETAP):
										self.put(self.startSample, self.samplenum, self.out_ann, [2, ['ETAP COMMAND: ' + INSTRUCTIONS[tempValueSent]]])
									else:
										self.put(self.startSample, self.samplenum, self.out_ann, [3, ['MTAP COMMAND: ' + INSTRUCTIONS[tempValueSent]]])
									if (tempValueSent == MTAP_SW_ETAP):
										self.selectedTAP = ETAP
									elif(tempValueSent == MTAP_SW_MTAP):
										self.selectedTAP = MTAP
									
									self.selectedRegister = tempValueSent
											
								self.onResetDeasserted()	

							elif(self.valueTMSstart == 	0x08):	# Should be more bit shifted. Eh. TODO later
								# If TMS value is 3b'100
								tempValueSent = self.valueTDI >> 3 # Cut off TMS HEADER. Damn LSBs
								tempValueSent = tempValueSent & ((2**((self.clockCycles - 2 - 3))) - 1 )	# -2 for cut off footer, -4 for command header
								tempValueReceived = self.valueTDO >> 3 # Cut off TMS HEADER. Damn LSBs
								tempValueReceived = tempValueReceived & ((2**((self.clockCycles - 2 - 3))) - 1 )	# -2 for cut off footer, -4 for command header
								print("Data sent was: " + str(tempValueSent) + " Data received was: " + str(tempValueReceived))

								if(self.selectedRegister == ETAP_FASTDATA):
								# Nope, because Pickit3 does 37 cycles, that [DELETED]
								#if (self.clockCycles == 38):	
								#	# 3+1+32+2
									print("Ping, doing XferFastData!")
									self.put(self.startSample, self.samplenum, self.out_ann, [6, ['FAST data ' + str(self.clockCycles - 2 - 4) + 'b, Sent: ' + str(hex(tempValueSent)) + ' Recvd: ' + str(hex(tempValueReceived))]])
									self.selectedRegister = E_MTAP_IDCODE

								else:
									print("Pong, doin XferData")
									

									if (self.selectedRegister == MTAP_COMMAND):
										if (tempValueSent in MTAP_COMMAND_DR):
											self.put(self.startSample, self.samplenum, self.out_ann, [4, ['COMMAND_DR: ' + MTAP_COMMAND_DR[tempValueSent]]])	
										else:
											self.put(self.startSample, self.samplenum, self.out_ann, [4, ['COMMAND_DR: Unknown :( ' + str(hex(tempValueSent))]])	
									else:
										self.put(self.startSample, self.samplenum, self.out_ann, [5, ['Data ' + str(self.clockCycles - 2 - 4) + 'b, Sent: ' + str(hex(tempValueSent)) + ' Recvd: ' + str(hex(tempValueReceived))]])								

								#time.sleep(5)
								self.onResetDeasserted()					
'''


	