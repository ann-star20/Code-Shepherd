def bad_function(a, b, c, d, e, f, g):  # 파라미터 과다
    unused = 42
    return a + b

def very_complex(a, b, c):
    if a:
        if b:
            if c:
                for i in range(10):
                    if i % 2:
                        if i > 5:
                            if a > b:
                                if b > c:
                                    if c > 0:
                                        if i != 7:   # 복잡도 11 달성
                                            return i
    return 0
