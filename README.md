# that_depends
Made after yet another package manager supply chain incident, npm has been taking huge Ls but so is pypi etc.
Lots of dependency chain attacks nowadays.

This is a [deps.dev](https://deps.dev) api wrapper to check their database.
If you know a package/version was compromised, and you have a dependency list for your project.
Useful for finding out if and what packages are affected.

Note: some 404s on package version lookup so just use it as a cursory glance.

# Configuration
Pre-run config should be configured in `config.py`:

## PACKAGE_SYSTEM 
choice of GO, RUBYGEMS, NPM, CARGO, MAVEN, PYPI, NUGET
e.g. `PACKAGE_SYSTEM = "PYPI"`

## TARGET_PACKAGE 
the target package name, (i.e. the package to check against in your `CHECK_LIST` config)
e.g. `TARGET_PACKAGE = "litellm"`

## TARGET_VERSION
the target package's version no. 
e.g. `TARGET_VERSION = "1.82.8"`

## CHECK_LIST
the list of packages (dependencies) to check against, for the given target.
NOTE: items must be in form `<package>` or `<package>==<version>` to work.
```python
CHECK_LIST = [
    "<package>==<version>",
    "<package>",
    ...
]
```

## MAX_CONCURRENT_REQUESTS
Maximum allowed concurrent http requests.
NOTE: keep this low, otherwise it stresses the api server. 
`MAX_CONCURRENT_REQUESTS = 5`

# Running
Then just run 
```python main.py```

and look at `./logs/`

# Logs 
## run_output 
general info for each package
## clean
packages that did not have target as a dependency 
## violations 
packages that did contain the target as part of its dependencies
## errors
packages that were unable to complete

## Could not fetch deps error
Probs means that deps.dev doesnt have that module recorded or something, usually a 404 for that package

# TODO
a) handle 404s theres lots

