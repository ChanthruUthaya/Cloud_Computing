import hashlib

def worker_function(combination, pwd):
    m = hashlib.md5()
    m.update(combination)
    return m.hexdigest() == pwd
