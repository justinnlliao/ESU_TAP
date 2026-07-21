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
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='jalia',
    maintainer_email='jalia@todo.todo',
    description='ROS 2 package for commanding and logging the ESU-TAP foot pedal interposer',
    license='TODO: License declaration',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'pedal_commander = pedal_controller.pedal_commander:main',
            'pedal_logger = pedal_controller.pedal_logger:main',
            # Test-only: software stand-in for the ESP32, for use before the
            # hardware arrives. Not flight code.
            'mock_esu_node = pedal_controller.mock_esu_node:main',
        ],
    },
)
