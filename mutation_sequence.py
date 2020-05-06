'''
Deserializes mutation sequence
data to a more easily
digestable format

USAGE EXAMPLE:
arr = np.array([[1,2,3], [4,5,6]])
ms = MutationSequence(numpy_matrix)
for mutation in ms:
    # Do something with mutation object
'''


class Mutation:

    END_OF_SEQUENCE = 17

    def __init__(self, serialized_params):
        '''
        serialized_params is a numpy array
        corresponding to the param array
        '''
        self.type = Mutation.END_OF_SEQUENCE
        pass


class BitFlip(Mutation):

    def __init__(self, serialized_params):
        self.type = 0
        self.position = serialized_params[1]


class SetByte(Mutation):

    def __init__(self, serialized_params):
        self.type = 1
        self.position = serialized_params[1]
        self.interesting_byte = serialized_params[2]


class SetWord(Mutation):

    def __init__(self, serialized_params):
        self.type = 2
        self.position = serialized_params[1]
        self.value = serialized_params[2]
        self.endian_swap = serialized_params[3]


class SetDWord(Mutation):

    def __init__(self, serialized_params):
        self.type = 3
        self.position = serialized_params[1]
        self.value = serialized_params[2]
        self.endian_swap = serialized_params[3]


class SubtractByte(Mutation):

    def __init__(self, serialized_params):
        self.type = 4
        self.position = serialized_params[1]
        self.subtract_value = serialized_params[2]


class AddByte(Mutation):

    def __init__(self, serialized_params):
        self.type = 5
        self.position = serialized_params[1]
        self.add_value = serialized_params[2]


class SubtractWord(Mutation):

    def __init__(self, serialized_params):
        self.type = 6
        self.position = serialized_params[1]
        self.subtract_value = serialized_params[2]
        self.endian_swap = serialized_params[3]


class AddWord(Mutation):

    def __init__(self, serialized_params):
        self.type = 7
        self.position = serialized_params[1]
        self.add_value = serialized_params[2]
        self.endian_swap = serialized_params[3]


class SubtractDWord(Mutation):

    def __init__(self, serialized_params):
        self.type = 8
        self.position = serialized_params[1]
        self.subtract_value = serialized_params[2]
        self.endian_swap = serialized_params[3]


class AddDWord(Mutation):

    def __init__(self, serialized_params):
        self.type = 9
        self.position = serialized_params[1]
        self.add_value = serialized_params[2]
        self.endian_swap = serialized_params[3]


class SetRandomByte(Mutation):

    def __init__(self, serialized_params):
        self.type = 10
        self.position = serialized_params[1]
        self.xor_value = serialized_params[2]


class DeleteBytes(Mutation):
    '''
    This can have a type of 11 or 12.
    '''

    def __init__(self, serialized_params):
        self.type = serialized_params[0]
        self.delete_length = serialized_params[1]
        self.delete_from = serialized_params[2]


class CloneOrInsert(Mutation):

    def __init__(self, serialized_params):
        self.type = 13
        self.cloned = serialized_params[1]
        self.clone_length = serialized_params[2]
        self.clone_from = serialized_params[3]

        # position and random_value aren't used
        # all the time, so we set values to None
        # where applicable
        self.use_random_value = None
        self.clone_position = None
        self.random_value = None
        if not self.cloned:
            self.use_random_value = serialized_params[4]
            if self.use_random_value:
                self.random_value = serialized_params[6]
            else:
                self.clone_position = serialized_params[5]


class OverwriteRandomOrFixed(Mutation):

    def __init__(self, serialized_params):
        self.type = 14
        self.overwrite_random = serialized_params[1]
        self.copy_len = serialized_params[2]
        self.copy_from = serialized_params[3]
        self.copy_to = serialized_params[4]

        self.use_random_value = None
        self.random_value = None
        self.position = None
        if not self.overwrite_random:
            self.use_random_value = serialized_params[5]
            if self.use_random_value:
                self.random_value = serialized_params[6]
            else:
                self.cloen_position = serialized_params[7]


class OverwriteBytesExtra(Mutation):

    def __init__(self, serialized_params):
        self.type = 15
        self.auto_or_dict = serialized_params[1]
        self.use_extra = serialized_params[2]
        self.extra_length = serialized_params[3]
        self.position = serialized_params[4]


class InsertExtra(Mutation):

    def __init__(self, serialized_params):
        self.type = 16
        self.auto_or_dict = serialized_params[1]
        self.use_extra = serialized_params[2]
        self.extra_length = serialized_params[3]
        self.position = serialized_params[4]


class MutationSequence:

    MUTATION_TYPE_MAP = {
        0: BitFlip,
        1: SetByte,
        2: SetWord,
        3: SetDWord,
        4: SubtractByte,
        5: AddByte,
        6: SubtractWord,
        7: AddWord,
        8: SubtractDWord,
        9: AddDWord,
        10: SetRandomByte,
        11: DeleteBytes,
        12: DeleteBytes,
        13: CloneOrInsert,
        14: OverwriteRandomOrFixed,
        15: OverwriteBytesExtra,
        16: InsertExtra
    }

    def __init__(self, serialized_mutations):
        '''
        Serialized mutation sequence
        represented as a numpy matrix.
        rows = mutations, cols = params per mutation
        '''
        self.sequence = []
        for serialized_mutation in serialized_mutations:
            m_type = serialized_mutation[0]
            if m_type == Mutation.END_OF_SEQUENCE:
                break
            m = MutationSequence.MUTATION_TYPE_MAP[m_type](serialized_mutation)
            self.sequence.append(m)

    def __iter__(self):
        return iter(self.sequence)
