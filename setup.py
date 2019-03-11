from setuptools import setup, find_packages

setup(
    name='bt_ccxt_store',
    version='1.0',
    description='A fork of Ed Bartosh\'s CCXT Store Work with some additions',
    url='https://github.com/Dave-Vallance/bt-ccxt-store',
    author='Dave Vallance',
    author_email='dave@backtest-rookies.com',
    license='MIT',
    packages=[find_packages()],
    install_requires=['backtrader', 'ccxt'],
    package_data={
        # If any package contains *.json files, include them:
        '': ['*.json'],
    },
)
