# simulator.py  0311/2014  D.J.Whale
#
# Simulate an LMC program.

import instruction
import loader
import io
import sys


BUS_MAX           = 999 # largest value the internal buses can use
PC_MAX            = BUS_MAX
STDIN_REDIRECTED  = not sys.stdin.isatty()
STDOUT_REDIRECTED = not sys.stdout.isatty()

program_counter   = 0
accumulator       = 0
b_reg             = 0
z_flag            = False # zero
p_flag            = False # positive
b_flag            = False # use A (if True, use B)
halt_flag         = False
memory            = {}


def trace(msg):
	print(str(msg))


def run(mem, startaddr = 0):
	"""Run a program to completion"""
	
	global program_counter, memory
	program_counter = startaddr
	memory = mem
	
	while not halt_flag:
		#TODO check LMC spec, does 999+1 wrap to 000?
		if program_counter < 0 or program_counter > 999:
			raise ValueError("out of range program counter:" 
			  + str(program_counter))
		cycle()


def cycle():
	"""Run a single cycle of the LMC machine"""

	global program_counter, accumulator, b_flag, b_reg
	
	# FETCH
	instr = fetch()
	##trace("fetch: pc:" + str(program_counter) + " instr:" + str(instr))
	program_counter = truncate(program_counter+1)
	
	# DECODE
	operator, operand = decode(instr)

	# If b_flag is set, read and write the B rather than the A
	if b_flag:
		acc = b_reg
	else:
		acc = accumulator
	
	# EXECUTE
	acc = execute(operator, operand, acc)

	# WRITE BACK
	if b_flag and instr != instruction.USB:
		b_reg = acc
		b_flag = False
	else:
		accumulator = acc


def fetch():
	"""Fetch a single instruction from memory at the program counter pos"""

	instr = memory[program_counter]
	return instr
	
	
def decode(instr):
	"""Decode a single instruction"""

	operator = instruction.getOperator(instr)
	operand = instruction.getOperand(instr)

	return operator, operand


def truncate(v):
	"""Truncate a value to the bus-width of the machine"""

	return v % (BUS_MAX+1)


def execute(operator, operand, acc):
	"""Execute a single instruction"""

	global program_counter, z_flag, p_flag, memory, halt_flag

	if   operator == instruction.HLT: # 0xx
		execTrapInstr(operand)

	elif operator == instruction.ADD: # 1xx
		acc += memory[operand]
		acc = truncate(acc)
		update_flags(acc)
		
	elif operator == instruction.SUB: # 2xx
		acc -= memory[operand]
		acc = truncate(acc)
		update_flags(acc)
		
	elif operator == instruction.STA: # 3xx
		memory[operand] = acc
		##trace("m[" + str(operand) + "]=" + str(acc))
		update_flags(acc)

	elif operator == instruction.EXT: # 4xx
		acc = execExtendedInstr(operand, acc)
		#Note, it does it's own update_flags if necessary
		
	elif operator == instruction.LDA: # 5xx
		acc = memory[operand]
		##trace("a=m[" + str(operand) + "]")
		update_flags(acc)
		
	elif operator == instruction.BRA: # 6xx
		program_counter = operand
		#??update_flags(operand)
		
	elif operator == instruction.BRZ: # 7xx
		if z_flag:
			program_counter = operand
			#??update_flags(operand)
			
	elif operator == instruction.BRP: # 8xx
		if p_flag:
			program_counter = operand
			#??update_flags(operand)

	elif operator == instruction.IO: # 9xx
		if operand == instruction.IO_IN: # 901
			if not STDIN_REDIRECTED:
				sys.stdout.write("in? ")
			value = io.read()
			#TODO: should we cope with negative numbers here and complement appropriately?
			#TODO: Should honour buswidth here depending on decimal/binary/hexadecimal io mode
			if value < 0 or value > 999:
				raise ValueError("Out of range value:" + str(value))
			acc = truncate(value)
			update_flags(acc)

		elif operand == instruction.IO_OUT: # 902
			if not STDOUT_REDIRECTED:
				sys.stdout.write("out=")
			io.write(acc)
			update_flags(acc)

		else: # user defined 9xx instructions
			execIOInstr(operand)

	else: # all might now be covered above??
		raise ValueError("Unknown operator:" + str(operator))

	return acc

		
def update_flags(v):
	"""Update the z and p flags"""
	
	global z_flag, p_flag
	
	if v == 0:
		z_flag = True
	else:
		z_flag = False
		
	
	#TODO check if LMC specifies how this is represented
	# negative is just a representation, so 000-999 are all positive,
	# but split into two halves. Not that easy to do two's complement,
	# so it should really be 10's complement??
	# 000-499 positive
	# 500-999 negative i.e. 999 is -1
	# so if >= 500, negative, value = 1000 = value
	# does the assembler allow entry of negative numbers, and code them
	# into the appropriate complemented form?
	
	if v < 500: #TODO: This will be dependent on buswidth
		p_flag = True
	else:
		p_flag = False


# EXTENDED INSTRUCTIONS ---------------------------------------------------
#
# This is a place that users can add their own instructions, while still
# being backwards compatible with the standard architecture.

# 000 is HLT but 001..099 are undefined. So, by modelling 0xx as a HLT
# and making HLT mean HLT 00, we can add HLT 01..HLT 99.
# Halts are useful for adding OS calls, for example, and might take
# a value in the accumulator to parameterise them, or the value in
# the accumulator might be a memory address that stores a block of
# parameters.

def execTrapInstr(operand):
	"""Execute any halt instructions here (instruction.T_XX)"""

	global halt_flag
	# Note that instruction.HLT is HLT 00 (000)
	if operand == 0:
		halt_flag = True
	else:
		raise ValueError("Unknown HLT instr:" + str(operand))
		# DEFINE TRAP INSTRUCTIONS HERE


# 5xx instructions are not defined, so these are USER instructions,
# The whole range from 500 to 599 are free for user use. U + 00
# to U + 99 can be used to add specific instruction extensions,
# such as bitwise operators and other useful facilities that would
# not normally be done with OS calls.


def execExtendedInstr(operand, acc):
	"""Execute any user instructions here (instruction.X_xx)"""

	if   operand == instruction.getOperand(instruction.USB): # Use Breg in next instruction
		global b_flag
		b_flag = True # next instr will use B instead of A

	elif operand == instruction.getOperand(instruction.MUL): # multiply
		acc = b_reg * acc
		update_flags(acc)

	elif operand == instruction.getOperand(instruction.DIV): # divide
		##trace("acc %d breg %d" % (acc, b_reg))
		acc = b_reg / acc
		update_flags(acc)

	else:
		raise ValueError("Unknown X instr:" + str(operand))

	return acc


# 901=INP and 902=OUT, but 900 and 903..999 are not used.
# These undefined instructions are therefore useful to use to define
# other types of IO, such as GPO for general purpose output, GPI for
# general purpose input, AIN for analog input, and other I/O
# related things that would not warrant a HLT for an OS call.
# they could be done as User instrutions (U) but it's handy to group
# all the I/O together into a set of instructions.

def execIOInstr(operand):
	"""Execute any user IO instructions here (instruction.IO_xx)"""

	raise ValueError("Unknown IO instr:" + str(operand))
	# DEFINE IO INSTRUCTIONS HERE


# MAIN PROGRAM ----------------------------------------------------------------

def main():
	FILENAME = sys.argv[1]
	m = {}
	loader.load(FILENAME, m)
	run(m)


if __name__ == "__main__":
	#TODO#### get encoder decoder settings from args io.configure()
	main()


# END


