#!/bin/bash
#
# Script to download the latest client versions.
#
# This script downloads the latest prebuilt agents from code.google.com/p/grr
# and installs them into the right place so that they can be used to build
# deployable agents.
#

PREFIX=/usr
REPO_BASE_URL=https://grr.googlecode.com/git

# EXE_DIR is where the executables and templates are stored
# Allow it to be overridden by environment variable.
if [ -z "${EXE_DIR}" ];
then
  EXE_DIR=${PREFIX}/share/grr/executables;
fi

# Variable to store if the user has answered "Yes to All"
if [ -z "${ALL_YES}" ];
then
  ALL_YES=0;
fi

function run_header() { echo "#### Running #### ${*}"; }

function exit_fail() {
  FAIL=$*;
  echo "#########################################################################################";
  echo "FAILURE RUNNING: ${FAIL}";
  echo "#########################################################################################";
  exit 0
};


function run_cmd_confirm()
{
  CMD=$*;
  echo ""
  if [ ${ALL_YES} = 0 ]; then
    read -p "Run ${CMD} [Y/n/a]? " REPLY
    case $REPLY in
      y|Y|'') run_header ${CMD};;
      a|A) echo "Answering yes from now on"; ALL_YES=1;;
      *) return ;;
    esac
  fi
  ${CMD};
  RETVAL=$?
  if [ $RETVAL -ne 0 ]; then
    exit_fail $CMD;
  fi
};

# Determine where to get the latest versions from.
if [ -z "${GRR_TEST_VERSIONS}" ];
then
  GRR_TEST_VERSIONS=0;
  VERSION_URL=https://grr.googlecode.com/files/latest_versions.txt
  VERSION_FILE=$(basename ${VERSION_URL})
  rm -f $VERSION_FILE
  run_cmd_confirm wget --no-verbose ${VERSION_URL};
elif [ $GRR_TEST_VERSIONS = 1 ]
then
  echo "Running with Beta test versions"
  VERSION_URL=https://grr.googlecode.com/files/latest_versions_test.txt
  VERSION_FILE=$(basename ${VERSION_URL})
  run_cmd_confirm wget --no-verbose ${VERSION_URL};
  rm -f $VERSION_FILE
else
  echo "Using $GRR_TEST_VERSIONS as version file"
  VERSION_FILE=$GRR_TEST_VERSIONS;
fi


echo "###############################################################"
echo "### Retrieving the latest list of clients and their packages"
echo "###############################################################"
WIN64_URL=$(grep client-win-64 ${VERSION_FILE} | cut -f 2);
WIN32_URL=$(grep client-win-32 ${VERSION_FILE} | cut -f 2);
OSX_URL=$(grep client-osx ${VERSION_FILE} | cut -f 2);

echo "###############################################################"
echo "### Windows clients"
echo "###############################################################"
# File will look like grr-installer-2204-64.zip and contain a directory named
# as the version, e.g. 2204
# 2204/grr.exe 2204/grrservice.exe 2204/....
run_cmd_confirm rm -f $(basename ${WIN64_URL});
run_cmd_confirm wget -N --no-verbose ${WIN64_URL};
run_cmd_confirm sudo unzip -o -d ${EXE_DIR}/windows/templates/win64 $(basename ${WIN64_URL});

rm -f $(basename ${WIN32_URL})
run_cmd_confirm wget -N --no-verbose ${WIN32_URL};
run_cmd_confirm sudo unzip -o -d ${EXE_DIR}/windows/templates/win32 $(basename ${WIN32_URL});


SFX_DIR=$EXE_DIR/windows/templates/unzipsfx/
sudo mkdir -p $EXE_DIR/windows/templates/unzipsfx;
if [ ! -f ${SFX_DIR}/unzipsfx-32.exe ]; then
  run_cmd_confirm wget --no-verbose -N ${REPO_BASE_URL}/executables/templates/windows/unzipsfx-32.exe;
  run_cmd_confirm wget --no-verbose -N ${REPO_BASE_URL}/executables/templates/windows/unzipsfx-64.exe;
  mv -f unzipsfx-32.exe ${SFX_DIR}
  mv -f unzipsfx-64.exe ${SFX_DIR}
fi

echo "###############################################################"
echo "### OSX client"
echo "###############################################################"
# File will look like grr-client-osx-2206.zip and contain a GRR.dmg file
# under a directory named as the version, e.g. 2206
# /2206/GRR.dmg
rm -f $(basename ${OSX_URL});
run_cmd_confirm wget -N --no-verbose ${OSX_URL};
if [ ! -d ${EXE_DIR}/darwin/templates ]; then
  run_cmd_confirm mkdir -p ${EXE_DIR}/darwin/templates
fi
run_cmd_confirm sudo unzip -o -d ${EXE_DIR}/darwin/templates $(basename ${OSX_URL});

echo "cleaning up downloaded files."
run_cmd_confirm rm -f $(basename ${WIN64_URL}) \
  $(basename ${WIN32_URL}) $(basename ${OSX_URL});


echo "################################################################"
echo "Done downloading clients."
echo "################################################################"
