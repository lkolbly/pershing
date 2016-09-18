from __future__ import print_function

from copy import deepcopy
import numpy as np

from util.blocks import block_names, Piston, Torch, Repeater

class Extractor:
    WIRE = 1
    REPEATER = 2
    UP_VIA = 3
    DOWN_VIA = 4
    NOOP = 5 # Placeholder between nets

    def extraction_to_string(extracted_net):
        d = {Extractor.WIRE: "WIRE",
             Extractor.REPEATER: "REPEATER",
             Extractor.UP_VIA: "UP_VIA",
             Extractor.DOWN_VIA: "DOWN_VIA"}
        return [d[i] for i in extracted_net]

    def __init__(self, blif, pregenerated_cells):
        self.blif = blif
        self.pregenerated_cells = pregenerated_cells

    def extract_net_segment(self, segment, start_pin, stop_pin):
        """
        Given the coordinates of the path of this net, generate the
        actual wire path, inserting repeaters as needed.
        """
        print(start_pin, stop_pin)

        def determine_movement(c1, c2):
            y1, z1, x1 = c1
            y2, z2, x2 = c2

            # Functions determining which is next
            def is_up_via():
                return (z1 == z2) and (x1 == x2) and (y2 - y1 == 3)

            def is_down_via():
                return (z1 == z2) and (x1 == x2) and (y2 - y1 == -3)

            def is_wire():
                """
                It's a wire if it moves in any of the compass directions and
                the change in Y is no more than one.
                """
                return abs(y1 - y2) <= 1 and \
                    ((x1 == x2 and abs(z1 - z2) == 1) or \
                     (z1 == z2 and abs(x1 - x2) == 1))

            if is_wire():
                return Extractor.WIRE
            elif is_up_via():
                return Extractor.UP_VIA
            elif is_down_via():
                return Extractor.DOWN_VIA
            else:
                print("Start is {}, stop is {}, segment is {}".format(start_pin, stop_pin, segment["net"]))
                raise ValueError("Unknown connection between {} and {}".format(c1, c2))
                return None

        # Actually 15, but assume that the gates have a margin of 2.
        # TODO: have gates define their output signal strength
        max_output_signal_strength = 13
        min_input_signal_strength = 1

        def generate_initial_extraction(net):
            # print(start_pin)
            # print(net)
            # print(stop_pin)

            # start_pin to 0
            extracted_net = [determine_movement(start_pin, net[0])]

            # (0 to 1) to (n-2 to n-1)
            for i in xrange(len(net)-1):
                c1, c2 = net[i], net[i+1]
                extracted_net.append(determine_movement(c1, c2))

            # n-1 to stop_pin
            extracted_net.append(determine_movement(net[-1], stop_pin))

            return extracted_net

        net_coords = segment["net"]
        initial_extraction = generate_initial_extraction(net_coords)

        # Split the extraction, determine redundant pieces (namely, the
        # wire-to-via connections), and then insert repeaters as needed.
        item, coords = self.split_extraction(initial_extraction, net_coords, start_pin, stop_pin)

        return zip(item, coords)

    def place_repeaters(self, extracted_net_subsection, coords, start_coord, stop_coord, start_strength=13, min_strength=1):
        """
        Place repeaters along this path until the final location has
        strength min_strength. min_strength must be at least 1.

        extracted_net_subsection is the list of [WIRE, WIRE, WIRE, ...]
        wire pieces to place repeaters along.

        start_coord and stop_coord are the coordinates of the coordinates
        immediately before and after (for usage with repeatable()).
        """

        subsection = list(extracted_net_subsection)

        print("Starting strength analysis: ", start_coord, start_strength)

        def repeatable(before, after):
            """
            A signal can be repeated as long as the block before the
            repeater and after the repeater form a line in X or Z.
            """
            yb, zb, xb = before
            ya, za, xa = after

            return yb == ya and \
                ((zb == za and abs(xb - xa) == 2) or \
                 (xb == xa and abs(zb - za) == 2))

        def compute_strength(subsection):
            if subsection == []:
                return []

            strengths = [0] * len(subsection)
            strengths[0] = start_strength
            i = 1
            while strengths[i-1] > 0 and i < len(strengths):
                if subsection[i] == Extractor.WIRE:
                    strengths[i] = strengths[i-1] - 1
                elif subsection[i] == Extractor.REPEATER:
                    strengths[i] = 16
                i += 1

            return strengths

        strengths = compute_strength(subsection)
        #while any(strength < min_strength for strength in strengths):
        while strengths[len(strengths)-1] < min_strength:
            # find candidate section, the first section where it is less than
            # the minimum strength
            repeater_i = strengths.index(min_strength - 1)

            while repeater_i >= 0:
                if repeater_i > 0:
                    before = coords[repeater_i - 1]
                else:
                    before = start_coord

                if repeater_i < len(coords) - 1:
                    after = coords[repeater_i + 1]
                else:
                    after = stop_coord

                if repeatable(before, after):
                    subsection[repeater_i] = Extractor.REPEATER
                    break
                else:
                    # move the repeater back
                    repeater_i -= 1

            if repeater_i < 0:
                raise ValueError("Cannot place repeaters to satisfy minimum strength.")

            strengths = compute_strength(subsection)

        # print("Placed repeaters:", subsection)
        return subsection, strengths[len(strengths)-1]

    def split_extraction(self, extracted_net, net_coords, start_coord, stop_coord):
        """
        Split up the extracted net based on sections of wire.
        """
        split_on = [[Extractor.REPEATER], [Extractor.WIRE, Extractor.UP_VIA], [Extractor.WIRE, Extractor.DOWN_VIA]]
        replacements = [[Extractor.REPEATER], [Extractor.UP_VIA], [Extractor.DOWN_VIA]]
        prev = 0
        curr = 0

        result = []
        coords = []

        # Try to find the sequences in split_on, and then chunk them up
        #print(extracted_net)
        #print(net_coords)
        #print(stop_coord)
        #last_strength = 13
        #strengths = {}
        while curr < len(extracted_net):
            found = False
            for candidate_split, replacement in zip(split_on, replacements):
                chunk_size = len(candidate_split)
                if extracted_net[curr:curr+chunk_size] == candidate_split:
                    # If it's a non-empty section, place repeaters
                    if prev != curr:
                        # Get the coordinates before and after this subsection (for repeaters)
                        before = start_coord if prev == 0 else net_coords[prev - 1]
                        after = net_coords[curr]

                        # Place the repeaters
                        repeated_subsection, _ = self.place_repeaters(extracted_net[prev:curr], net_coords[prev:curr], before, after)
                        result.append(repeated_subsection)
                        coords.append(net_coords[prev:curr])

                    # Place the replacement section (using the coordinate of the first part)
                    result.append(replacement)
                    coords.append(net_coords[curr:curr+1])

                    # Update indices
                    curr += chunk_size
                    prev = curr

                    found = True
                    break

            if not found:
                curr += 1

        # Add the last section, unless it's empty (prev == curr)
        before = net_coords[prev - 1]
        result.append(self.place_repeaters(extracted_net[prev:curr], net_coords[prev:curr], before, stop_coord)[0])
        coords.append(net_coords[prev:curr])

        return sum(result, []), sum(coords, [])

    def place_blocks(self, extracted_net, layout, pins):
        """
        Modify layout to have the extracted net.
        """
        redstone_wire = block_names.index("redstone_wire")
        stone = block_names.index("stone")
        planks = block_names.index("planks")
        sticky_piston = block_names.index("sticky_piston")
        unpowered_repeater = block_names.index("unpowered_repeater")
        redstone_torch = block_names.index("redstone_torch")
        unlit_redstone_torch = block_names.index("unlit_redstone_torch")
        redstone_block = block_names.index("redstone_block")
        air = block_names.index("air")

        blocks, data = layout

        def repeater_facing(z, x, z1, x1):
            """
            Given an (x, z) of a repeater and the (x1, z1) of the block
            before it, compute the direction the repeater faces.
            """
            if (z > z1): 
                return Repeater.SOUTH
            elif (z < z1):
                return Repeater.NORTH
            elif (x > x1):
                return Repeater.EAST
            elif (x < x1):
                return Repeater.WEST
            else:
                raise ValueError("Repeater and previous block have same placement")

        # De-duplicate everything
        things = {Extractor.WIRE: {}, Extractor.REPEATER: {}, Extractor.UP_VIA: {}, Extractor.DOWN_VIA: {}, Extractor.NOOP: {}}
        for i, (extraction_type, placement) in enumerate(extracted_net):
            y, z, x = placement
            things[extraction_type][y,z,x] = i

            if extraction_type != Extractor.NOOP:
                # Fill in the stone basement, while we're at it
                blocks[y-1, z, x] = stone if y == 1 else planks

        # Run wires
        for (y,z,x), i in things[Extractor.WIRE].items():
            if len(extracted_net) > i+1:
                _, next_placement = extracted_net[i+1]
            else:
                next_placement = (-1,-1,-1)
            if len(extracted_net) > i+2:
                t_after, _ = extracted_net[i+2]
            else:
                t_after = Extractor.NOOP
            if (y,z,x) in things[Extractor.REPEATER]:
                continue # Don't stick a wire where we have a repeater
            # If the next place has an up via, AND we're on the down side.
            # This is because up vias are weakly powered, so we need a repeater
            # to power through them.
            # Also, if we're an input pin, then the routes are for some reason
            # backward, so we don't want a repeater.
            t, prev_placement = extracted_net[i-1]
            _, z1, x1 = prev_placement
            if tuple(next_placement) in things[Extractor.UP_VIA] and y == next_placement[0] and (y,z,x) not in pins:
                # We have to make ourselves a repeater
                blocks[y, z, x] = unpowered_repeater
                if t == Extractor.NOOP:
                    _, z1, x1 = next_placement
                    facing = repeater_facing(z1,x1, z,x)
                else:
                    facing = repeater_facing(z,x, z1,x1)
                data[y, z, x] = facing
            else:
                blocks[y,z,x] = redstone_wire

        # Run repeaters
        for (y,z,x), i in things[Extractor.REPEATER].items():
            blocks[y, z, x] = unpowered_repeater
            t, prev_placement = extracted_net[i-1]
            t1, z1, x1 = prev_placement
            data[y,z,x] = repeater_facing(z,x, z1,x1)

        # Run down vias
        for (y,z,x), _ in things[Extractor.DOWN_VIA].items():
            blocks[y-1, z, x] = sticky_piston
            blocks[y-2, z, x] = redstone_block
            blocks[y-3, z, x] = air
            blocks[y-4, z, x] = stone

        # Run up vias
        for (y,z,x), _ in things[Extractor.UP_VIA].items():
            blocks[y-1, z, x] = stone
            blocks[y  , z, x] = stone
            blocks[y+1, z, x] = redstone_torch
            data[y+1, z, x] = Torch.UP
            blocks[y+2, z, x] = planks
            blocks[y+3, z, x] = unlit_redstone_torch
            data[y+3, z, x] = Torch.UP

        # For each of the types, place
        """for i, (extraction_type, placement) in enumerate(extracted_net):
            y, z, x = placement
            if extraction_type == Extractor.WIRE:
                print("wire: %d,%d,%d"%(x,z,y))
                blocks[y  , z, x] = redstone_wire
                blocks[y-1, z, x] = stone if y == 1 else planks
            elif extraction_type == Extractor.REPEATER:
                blocks[y  , z, x] = unpowered_repeater
                # determine orientation of repeater
                _, prev_placement = extracted_net[i-1]
                _, z1, x1 = prev_placement
                data[y  , z, x] = repeater_facing(z, x, z1, x1)
                blocks[y-1, z, x] = stone if y == 1 else planks
            elif extraction_type == Extractor.UP_VIA:
                print("up_via: %d,%d,%d"%(x,z,y))
                blocks[y-1, z, x] = stone
                blocks[y  , z, x] = stone
                blocks[y+1, z, x] = redstone_torch
                data[y+1, z, x] = Torch.UP
                blocks[y+2, z, x] = planks
                blocks[y+3, z, x] = unlit_redstone_torch
                data[y+3, z, x] = Torch.UP
            elif extraction_type == Extractor.DOWN_VIA:
            blocks[y  , z, x] = sticky_piston
                blocks[y-1, z, x] = redstone_block
                blocks[y-2, z, x] = air
                blocks[y-3, z, x] = redstone_wire
                blocks[y-4, z, x] = stone
                blocks[y-1, z, x] = sticky_piston
                blocks[y-2, z, x] = redstone_block
                blocks[y-3, z, x] = air
                blocks[y-4, z, x] = stone
            else:
                raise ValueError("Unknown extraction type", extraction_type)"""

    def extract_routing(self, routing):
        """
        Place the wires and vias specified by routing.
        """
        routing = deepcopy(routing)
        for net_name, d in routing.iteritems():
            for segment in d["segments"]:
                endpoints = segment["pins"]
                start_pin = endpoints[0]["pin_coord"]
                stop_pin = endpoints[1]["pin_coord"]

                extracted_net = self.extract_net_segment(segment, start_pin, stop_pin)
                segment["extracted_net"] = [(Extractor.WIRE, start_pin)] + extracted_net + [(Extractor.WIRE, stop_pin)]

        return routing

    def extract_layout(self, extracted_routing, placed_layout):
        """
        Place the wires and vias specified by routing.
        """
        blocks, data = placed_layout
        extracted_blocks = np.copy(blocks)
        extracted_data   = np.copy(data)
        extracted_layout = (extracted_blocks, extracted_data)

        total_net = []
        pins = set()
        for net_name, d in extracted_routing.iteritems():
            for segment in d["segments"]:
                #self.place_blocks(segment["extracted_net"], extracted_layout)
                total_net += segment["extracted_net"]
                total_net += [(Extractor.NOOP, (-2,-2,-2))]
                pins.update(map(lambda p: tuple(p["pin_coord"]), segment["pins"]))
        self.place_blocks(total_net, extracted_layout, pins)

        return extracted_layout
