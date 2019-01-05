from setuptools import setup

setup(
   name='bt_ccxt_store',
   version='1.0',
   description='A fork of Ed Bartosh\'s CCXT Store Work with some additions',
   url='https://github.com/Dave-Vallance/bt-ccxt-store',
   author='Dave Vallance',
#   author_email='foomail@foo.com',
   license='MIT',
   packages=['ccxtbt'],  
   install_requires=['backtrader','ccxt'], 
)
