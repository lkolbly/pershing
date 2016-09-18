PlacE RedStone Hardware IN Game (PERSHING)
==========================================
PERSHING (formerly called MPRT) accepts Berkeley Logic Interchange Files
(BLIFs) and produces a compacted layout of logic cells and the redstone wire
connections needed to produce a functioning circuit in Minecraft.

		       Verilog file (*.v)
			       |
			       |  yosys (not this repo)
			       V
		       BLIF file (*.blif)
			       |
			       |  PERSHING (this repo)
			       V
		 Fully placed-and-routed layout
			       |
			       |  inserter.py (this repo too)
			       V
			   Minecraft

Combined with a synthesis tool like Yosys, PERSHING can accept Verilog and
produce functional circuits, paving the way for vastly more complex circuits
than can be manually laid by hand.

Requirements
------------
- Yosys (or another way to create BLIFs)
- Python 2.7
- NBT

Setup
-----
To read/write Minecraft worlds, we use the [NBT package](https://github.com/twoolie/NBT).
Initialize it with the `git submodule` command.

	$ git submodule update --init

You must also already have `yosys` installed.

Also, you must put a texture pack in the top directory, and call it "texturepack.zip"

Usage
-----
The easiest way to use PERSHING is to use the convenience script `main.sh`:

	$ ./main.sh <input Verilog file>

Known Issues
------------
Here are some known issues to look out for when generating designs:
- If a wire segment goes to an input pin, and then another wire segment starts at that input pin and goes somewhere else, sometimes (if they're long enough) the second wire segment doesn't get generated with enough repeaters, and the signal won't reach the end. In principle this could affect timing results as well, so be careful.
- If there is an upward via (the torch stack) adjacent to an input pin, sometimes the input pin will generate a repeater pointing at the via, preventing the signal from going into the logic cell. If this happens replace the repeater with a redstone wire.
- If you use this program to generate a world (as opposed to generate a world, and then copy that world into a survival map by hand), NOT gates (the 1x4 gates) will need a block update on the output before they work.
- Once in a long while, a straight wire will pass by an upward via (as opposed to into it), so the via won't receive the signal. The via would need to be moved in this case. This is because this isn't technically a violation, although the router does try to minimize how much this happens, so it should be a very rare occurrance.

This was all tested using craftbukkit 1.8.

Advanced Users
--------------
For finer-grained control, including resuming partial runs, execute `main.py`
at the command line. Below is the help text:

	main.py [-h] [-o output_directory] [--library library_file]
	    [--placements placements_file] [--routings routings_file]
	    [--world world_folder]
	    <input BLIF file>

To generate BLIF files (using Yosys), run `yosys.sh`:

	$ ./yosys.sh <input Verilog file>

The resulting BLIF file is the name of the Verilog file without the suffix, and
with `.blif` added. Then, to run PERSHING, use:

	$ ./main.py <output blif file>

Why is it called PERSHING?
--------------------------
The [MGM-31A Pershing ballistic missle system](https://en.wikipedia.org/wiki/MGM-31_Pershing)
succeeded the United States' Redstone ballistic missle system in the 1960s. In a
project involving Redstone, "Pershing" sounds pretty cool.

Other Notes
-----------
A publication resulting from the creation of this project appeared at the first
annual conference on TBD ([SIGTBD](http://sigtbd.csail.mit.edu/)), a joke
conference at MIT.
