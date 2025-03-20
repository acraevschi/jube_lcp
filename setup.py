from setuptools import setup, find_packages

setup(
    name="jube_prep",
    version="0.1.0",
    package_data={"jube_prep": ["meta.json"]},
    include_package_data=True,
    packages=find_packages(),
    python_requires=">=3.11,<3.12",
    install_requires=[
        "pandas>=2.2.0,<3.0.0",
    ],
    entry_points={
        "console_scripts": [
            "jube_prep=jube_prep.xml_to_conllu:main",
        ],
    },
)
