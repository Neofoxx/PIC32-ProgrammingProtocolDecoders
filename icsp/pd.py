'''
Microchip ICSP decoder, with 4-phase supprt (2-phase is not supported)
Everything is CLOCK driven
-> First there needs to be a Reset, to get into a known state
-> Then there should be an entry pattern
-> Then we go on.
'''

import sigrokdecode as srd
import time

STATE_PRE_RESET, STATE_RESET, STATE_POST_RESET, STATE_AGGREGATING_DATA = range(4)	# Definition of global states
PIN_RESET, PIN_CLOCK, PIN_DATA = range(3)	# Pins
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


class Decoder(srd.Decoder):
	api_version = 3
	id = 'icsp'
	name = 'ICSP'
	longname = 'Microchip PIC32 ICSP (4-phase)'
	desc = 'PIC32 programming protocol-'
	license = 'gplv2+'
	inputs = ['logic']
	outputs = ['icsp']
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
		('tap-reset', 'TAP reset'),					# 8
		
	)
	anotation_rows = (
		('tap-state', 'TAP', (0,)),
		('command', 'Command', (0,)),
	
	)

	def __init__(self):
		self.state = STATE_PRE_RESET
		# Vars used globally
		self.startSample = 0

		# Vars used during reset
		self.value = 0
		self.clockCycles = 0

		# Vars used during post-reset
		self.valueTDI = 0
		self.valueTDO = 0
		self.valueTMS = 0
		self.subClockCycles = 0
		print("HERE 0");

	def start(self):
		self.out_ann = self.register(srd.OUTPUT_ANN)
		self.value = 0
		self.clkCycles = 0
		self.valueTDI = 0
		self.valueTDO = 0
		self.valueTMS = 0
		self.clockCycles = 0	
		self.subClockCycles = 0;
		self.selectedTAP = 0;
		self.selectedRegister = 0;
		self.enteredICSP = 0
		print("HERE 1");
		
	def onResetAsserted(self):
		self.value = 0
		self.clkCycles = 0
		self.startSample = self.samplenum

	def onResetDeasserted(self):
		self.valueTDI = 0
		self.valueTDO = 0
		self.valueTMS = 0
		self.clockCycles = 0	
		self.subClockCycles = 0;
		#self.selectedTAP = 0;
		#self.selectedRegister = 0;
		self.startSample = self.samplenum


	def decode(self):
		print("HERE 2");
		
		while True:
			#time.sleep(0.01)
			conds = []
			print("STATE IS: " + str(self.state))
			if (self.state == STATE_PRE_RESET):
				# RESET asserted
				conds.append({PIN_RESET: 'f'})	# On falling edge
				self.wait(conds)
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
					#time.sleep(1)
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



	
