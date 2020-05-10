import datetime
from subprocess import PIPE, run
from .solution import Solution


def verifyOutput(file1, file2, tempdir):
    # verify equivalence using ABC
    print('Verifying equivalence of {} and {}'.format(file1,file2))
    with open(tempdir + "abcverify", "w") as f:
        f.write("cec {} {}".format(file1, file2))
    command = ["abc", "-f", tempdir + "abcverify"]
    result = run(command, stdout=PIPE, stderr=PIPE, universal_newlines=True)
    print('Verifying completed with return code {}'.format(result.returncode))
    output = result.stdout
    if result.returncode != 0:
        return False, result.stderr
    else:

        if "are equivalent" in output:
            print(
                "Files {} and {} are logically equivalent".format(file1, file2)
            )
            return True, output
        else:
            print(
                "Files {} and {} are logically not equivalent".format(
                    file1, file2
                )
            )
            return False, output


class MappingSolExplorer:
    def __init__(
        self, steps, lutGraph, R,C, alloc, posOutAlloc, debug=False, sol=None
    ):
        self.__steps = steps
        self.__lutGraph = lutGraph
        self.__R = R
        self.__C = C
        self.__alloc = alloc
        self.__posOutAlloc = posOutAlloc
        self.__debug = False
        self.__log = Solution()
        

    def __getSteps(self):
        """ provides a detailed breakdown of the types of steps """
        stepCount = dict()
        opTrack = dict()

        """ Some examples:
        ['COPY', (7, 20), (22, 20), '67']
        ['VNOR', [(16, 7), (17, 7), (18, 7)], 'lut42']
        ['VNOT', [(19, 7), (20, 7)], 'lut65']
        [['HNOR', [(4, 0), (4, 1), (4, 2), (4, 3), (4, 5), (4, 7), (4, 8)], 'I38'], 
        ['HNOR', [(5, 0), (5, 1), (5, 2), (5, 3), (5, 5), (5, 7), (5, 8)], 'I38'],
        ['HNOR', [(6, 0), (6, 1), (6, 2), (6, 3), (6, 5), (6, 7), (6, 8)], 'I38']]
        ['INPUT', (9, 7), 'x']
        [['NOT', [(8, 8), (8, 0)], 'q0'], ['NOT', [(15, 8), (15, 0)], 's0'], ['NOT', [(25, 8), (25, 0)], 't0']]
        """

        for s in self.__steps:
            if self.__debug:
                print(s)
            if type(s[0]) is list:
                # parallel operations
                opType = s[0][0]
                opCount = len(s)
            else:
                opType = s[0]
                opCount = 1

            if opType in stepCount.keys():

                stepCount[opType] = stepCount[opType] + 1
                opTrack[opType] = opTrack[opType] + opCount
            else:
                stepCount[opType] = 1
                opTrack[opType] = opCount
        return stepCount, opTrack

    def writeVerilog(self, modulename, outfile):
        """ Writes a Verilog file """
        R, C = self.__R, self.__C
        header = "// Generated by Arche for {} for crossbar {}x{} \n".format(
            modulename, R, C
        )
        header = header + "// Printed on {}\n".format(datetime.datetime.now())
        header = header + "module {}(\n".format(modulename)
        inpHeader = "input "
        for i in self.__lutGraph["inputs"][:-1]:
            header = header + "{} , ".format(i)
            inpHeader = inpHeader + " {} , ".format(i)
        header = header + "{} , ".format(self.__lutGraph["inputs"][-1])
        inpHeader = inpHeader + "{} ;\n ".format(self.__lutGraph["inputs"][-1])

        outHeader = "output "
        for j in self.__lutGraph["outputs"][:-1]:
            header = header + "{} , ".format(j)
            outHeader = outHeader + "{} , ".format(j)

        header = header + self.__lutGraph["outputs"][-1]
        outHeader = outHeader + " {} ;\n".format(
            self.__lutGraph["outputs"][-1]
        )

        header = header + ");\n"

        wires = []
        wc = 0
        footer = "endmodule\n"

        state = dict()  # state[(r,c)] = varname
        usage = dict()
        for r in range(R):
            for c in range(C):
                state[(r, c)] = "1"
                usage[(r, c)] = 0

        content = ""
        for s in self.__steps:

            if type(s[0]) == list:  # multiple operations scheduled

                for operation in s:
                    wc = wc + 1
                    w = "tempW" + str(wc)
                    wires.append(w)
                    assign = self.__getOpString(
                        w, operation, state, usage, R, C
                    )
                    if assign == None:
                        self.__log.addParam(
                            "error", "Invalid operation encountered"
                        )
                        return False
                    content = content + assign

            else:  # single operation scheduled
                wc = wc + 1
                w = "tempW" + str(wc)

                assign = self.__getOpString(w, s, state, usage, R, C)
                if assign == None:
                    self.__log.addParam(
                        "error", "Invalid operation encountered"
                    )
                    return False
                elif assign != "":
                    wires.append(w)
                if s[0] == "reset":
                    for r in range(R):
                        for c in range(C):
                            if self.__debug:
                                print(state[(r, c)], end=" ")
                        if self.__debug:
                            print("", end="\n")

                content = content + assign
        wireHeader = "wire "
        for wire in wires:
            wireHeader = wireHeader + " {} ,".format(wire)
        wireHeader = wireHeader[:-1] + "; \n"

        with open(outfile, "w") as f:
            f.write(header)
            f.write(inpHeader)
            f.write(outHeader)
            f.write(wireHeader)
            f.write(content)

            for outName in self.__lutGraph["outputs"]:
                vout = self.__lutGraph.vs.select(name=outName)[0]
                vertex = vout.index
                if vout["lut"].isConstant():
                    if vout["lut"].isConstant() == "one":
                        s = "1"
                    else:
                        s = "0"
                else:
                    loc = self.__posOutAlloc[vertex]
                    s = state[(loc[0], loc[1])]
                print(loc, s, outName)
                f.write("assign {} = {} ;\n".format(outName, s))
                # print('{} -> {}: {}'.format(outName,vout,s))

            f.write(footer)
            
        # replace all " 1 " and " 0 " with " 1'b1 " and "1'b0"
        with open(outfile, "r") as f:
            data = f.read()

        data = data.replace(" 1 ", " 1'b1 ")
        data = data.replace(" 0 ", " 1'b0 ")
        with open(outfile, "w") as f:
            f.write(data)
        # print('alloc: {} outputs: {}'.format(alloc, lutGraph['outputs']))

    def __getOpString(self, w, operation, state, usage, R, C):
        """ returns the Verilog statement corresponding to the operation """
        op = []
        for v in operation:
            if type(v) == list:
                for v1 in v:
                    op.append(v1)
            else:
                op.append(v)

        if self.__debug:
            print("op: {}".format(op))
        assign = ""
        operation = op
        if operation[0] == "reset":  # just update the state
            if operation[-1] == "r":
                for r in operation[1:-1]:
                    for c in range(C):
                        state[(r, c)] = "1"
                return ""
            elif operation[-1] == "c":
                for r in range(R):
                    for c in operation[1:-1]:
                        state[(r, c)] = "1"
                return ""
            else:
                print("Error: Invalid operation {}".format(operation))
                return None

        dest = operation[-2]
        if self.__debug:
            print("dest:{} w:{}".format(dest, w))

        if operation[0] != "SETZERO" and state[dest] != "1":
            print(
                "Error: Writing to a dirty position {} Content: {}".format(
                    dest, state[dest]
                )
            )

            return None
        state[dest] = w

        if (
            operation[0] == "COPY"
            or operation[0] == "VNOT"
            or operation[0] == "NOT"
        ):
            # only two positions
            op = operation[1]
            if not (op[0] == dest[0] or op[1] == dest[1]):
                print(
                    "Error: {} operands not aligned {}".format(
                        operation[0], operation
                    )
                )
                return None
            assign = "assign {} = ~ {} ;\n".format(w, state[op])
            usage[op] = usage[op] + 1

        elif operation[0] == "VNOR" or operation[0] == "HNOR":
            opCount = len(operation) - 3  # opcode op1 op2 ... opn dest label
            assign = "assign {} = ~( ".format(w)
            for i in range(opCount):
                if not (
                    operation[i + 1][0] == operation[i + 2][0]
                    or operation[i + 1][1] == operation[i + 2][1]
                ):

                    print(
                        "Error: {} operands not aligned {}".format(
                            operation[0], operation
                        )
                    )
                    return None
            newOps = []
            for i in range(opCount):
                if state[operation[i + 1]] != "0":
                    newOps.append(state[operation[i + 1]])
                usage[operation[i + 1]] = usage[operation[i + 1]] + 1

            opCount = len(newOps)
            for i in range(opCount):

                if i == opCount - 1:
                    assign = assign + " {} ) ; // {}\n ".format(
                        newOps[i], operation[-1]
                    )

                else:
                    assign = assign + " {} |".format(newOps[i])

        elif operation[0] == "INPUT":
            state[dest] = operation[-1]
        elif operation[0] == "SETZERO":
            for loc in operation[1:-1]:
                state[loc] = "0"
        else:
            print("Error: Invalid operation {}".format(operation))
            return None
        usage[dest] = usage[dest] + 1
        return assign
    
    def getSteps(self,steps):
        ''' provides a detailed breakdown of the types of steps ''' 
        stepCount = dict()
        opTrack = dict()
        
        ''' Some examples:
        ['COPY', (7, 20), (22, 20), '67']
        ['VNOR', [(16, 7), (17, 7), (18, 7)], 'lut42']
        ['VNOT', [(19, 7), (20, 7)], 'lut65']
        [['HNOR', [(4, 0), (4, 1), (4, 2), (4, 3), (4, 5), (4, 7), (4, 8)], 'I38'], 
        ['HNOR', [(5, 0), (5, 1), (5, 2), (5, 3), (5, 5), (5, 7), (5, 8)], 'I38'],
        ['HNOR', [(6, 0), (6, 1), (6, 2), (6, 3), (6, 5), (6, 7), (6, 8)], 'I38']]
        ['INPUT', (9, 7), 'x']
        [['NOT', [(8, 8), (8, 0)], 'q0'], ['NOT', [(15, 8), (15, 0)], 's0'], ['NOT', [(25, 8), (25, 0)], 't0']]
        '''

        for s in steps:
            if self.__debug: print(s)
            if type(s[0]) is list:
                # parallel operations
                opType = s[0][0]
                opCount = len(s)
            else:
                opType = s[0]
                opCount = 1
            
            
            if opType in stepCount.keys():
                
                    
                stepCount[opType] = stepCount[opType] + 1
                opTrack[opType] = opTrack[opType] + opCount 
            else:
                stepCount[opType] = 1
                opTrack[opType] = opCount 
        return stepCount, opTrack
    
    def writeSteps(self,steps,outfile):
        with open(outfile,'w') as f:
            t = 0
            for s in steps:
                t = t+1
                f.write('T{} '.format(t))
                for v in s:
                    if type(v) == list:
                        for val in v:
                            if type(val) == list:
                                for vin in val:
                                    f.write('{} '.format(vin))
                            else:
                                f.write('{} '.format(val))
                        f.write(' | ')
                    else:
                        f.write('{} '.format(v))


                f.write('\n')
    
