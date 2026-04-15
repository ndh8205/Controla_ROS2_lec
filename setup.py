import os
from setuptools import setup, find_packages

package_name = 'orbit_sim'

def package_files(directory):
    """
    Recursively finds all files in a directory and prepares them for setup.py data_files.
    This preserves the entire directory structure.
    """
    paths = []
    for (path, directories, filenames) in os.walk(directory):
        for filename in filenames:
            # Create a tuple of (destination_directory, [source_files])
            # The destination is relative to the package's share directory
            dest_dir = os.path.join('share', package_name, path)
            src_file = os.path.join(path, filename)
            paths.append((dest_dir, [src_file]))
    return paths

# Create the list of data_files by walking through the 'models', 'worlds', 'launch', and 'data' directories
data_files_list = package_files('models')
data_files_list.extend(package_files('worlds'))
data_files_list.extend(package_files('launch'))
data_files_list.extend(package_files('data'))

# Add package.xml and resource file
data_files_list.append(('share/ament_index/resource_index/packages', ['resource/' + package_name]))
data_files_list.append(('share/' + package_name, ['package.xml']))


setup(
    name=package_name,
    version='0.0.1',
    packages=find_packages(exclude=['test']),
    data_files=data_files_list,
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='your_name',
    maintainer_email='your_email@example.com',
    description='Integrated orbit simulation package for Space ROS',
    license='Apache License 2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'multi_satellite_controller = orbit_sim.multi_satellite_controller:main',
            'gco_controller = orbit_sim.gco_controller:main',
            'orbit_LVLH_gco = orbit_sim.orbit_LVLH_gco:main',
        ],
    },
)