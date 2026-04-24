from setuptools import setup

package_name = 'pedal_controller'

setup(
    name=package_name,
    version='0.0.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', ['launch/esu_serial_bridge.launch.py']),
    ],
    install_requires=['setuptools', 'pyserial'],
    zip_safe=True,
    maintainer='jalia',
    maintainer_email='jalia@todo.todo',
    description='ROS 2 package for actuating and logging Da Vinci foot pedal',
    license='TODO: License declaration',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'pedal_commander = pedal_controller.pedal_commander:main',
            'pedal_logger = pedal_controller.pedal_logger:main',
            'esu_serial_bridge = pedal_controller.esu_serial_bridge:main',
        ],
    },
)
