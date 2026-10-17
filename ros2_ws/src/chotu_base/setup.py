from setuptools import setup

package_name = "chotu_base"

setup(
    name=package_name,
    version="2.0.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
    ],
    install_requires=["setuptools", "pyserial"],
    zip_safe=True,
    maintainer="Gurjas Singh Gandhi",
    maintainer_email="gurjasgandhi76@gmail.com",
    description="CHOTU hardware bridge (ESP32-S3 serial link) and Gazebo sensor adapter",
    license="MIT",
    tests_require=["pytest"],
    entry_points={"console_scripts": [
        "serial_bridge_node = chotu_base.serial_bridge_node:main",
        "gz_sensor_adapter_node = chotu_base.gz_sensor_adapter_node:main",
    ]},
)
