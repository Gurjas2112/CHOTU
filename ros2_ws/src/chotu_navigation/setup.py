from setuptools import setup

package_name = "chotu_navigation"

setup(
    name=package_name,
    version="2.0.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
    ],
    install_requires=["setuptools", "numpy"],
    zip_safe=True,
    maintainer="Gurjas Singh Gandhi",
    maintainer_email="gurjasgandhi76@gmail.com",
    description="CHOTU mission manager (wraps chotu_core.CleaningMission)",
    license="MIT",
    entry_points={"console_scripts": [
        "mission_manager_node = chotu_navigation.mission_manager_node:main",
    ]},
)
