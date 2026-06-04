class _Comparison:
    def __init__(self, column_name, value):
        self.column_name = column_name
        self.value = value


class _Column:
    def __init__(self, name):
        self.name = name

    def __eq__(self, other):
        return _Comparison(self.name, other)


class Product:
    id = _Column("id")

    def __init__(self, id, name):
        self._id = id
        self.name = name
