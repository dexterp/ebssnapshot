import metadata

if __name__ == '__main__':
    # Provide a simple way to find version for Makefiles.
    # This method is preferred over python setup.py --version
    # because it has no Pypi dependencies at runtime.
    print metadata.__version__
