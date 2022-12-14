# -*- Autoconf -*-
# $Id$

AC_PREREQ([2.61])
AC_INIT([rpkitools], [1.0])

# AC_REVISION is a great idea in theory, but the revision will always
# be wrong unless we do two checkins, so skip it for now.  Someday.

dnl AC_REVISION([$Revision$])

AC_CONFIG_SRCDIR([rp/rcynic/rcynic.c])
AC_CONFIG_AUX_DIR([buildtools])

# I'm not sure we should really be using the $host_* variables as we
# are, some of the stuff we're doing with them looks more like
# $target_* to me now, but on the theory that we should not fix things
# that aren't broken, stick with $host_* for now.

AC_CANONICAL_HOST
dnl AC_CANONICAL_TARGET

# Remember whether CFLAGS or LDFLAGS were set explictly.  This has to
# come early in the script, before we mess it up testing things.

if test "x${CFLAGS+set}" = "x" && test "x${LDFLAGS+set}" = "x"
then
	CFLAGS_or_LDFLAGS_were_set=no
else
	CFLAGS_or_LDFLAGS_were_set=yes
fi

# Put the user option stuff up front.

AC_ARG_WITH([system_openssl],		[AS_HELP_STRING([--with-system-openssl],			[Link against system copy of OpenSSL])],        [], [with_system_openssl=auto])
AC_ARG_ENABLE([openssl_asm],		[AS_HELP_STRING([--disable-openssl-asm],			[Don't let OpenSSL build assembler code])],     [], [enable_openssl_asm=auto])
AC_ARG_ENABLE([ca_tools],		[AS_HELP_STRING([--disable-ca-tools],				[Don't build any of the CA tools])],            [], [enable_ca_tools=yes])
AC_ARG_ENABLE([rp_tools],		[AS_HELP_STRING([--disable-rp-tools],				[Don't build any of the relying party tools])], [], [enable_rp_tools=yes])
AC_ARG_ENABLE([target_installation],	[AS_HELP_STRING([--disable-target-installation],		[Don't perform final target installation])],    [], [enable_target_installation=yes])
AC_ARG_ENABLE([wsgi_daemon_mode],	[AS_HELP_STRING([--enable-wsgi-daemon-mode=user[[:group]]],	[Run the web portal as a separate process])],   [], [enable_wsgi_daemon_mode=no])
AC_ARG_ENABLE([python_install_layout],	[AS_HELP_STRING([--enable-python-install-layout=layout],	[Specify Python --install-layout])],		[], [enable_python_install_layout=auto])
AC_ARG_ENABLE([wsgi_python_egg_cache],  [AS_HELP_STRING([--enable-wsgi-python-egg-cache=dir[[:user]]],	[Set up PYTHON_EGG_CACHE in wsgi wrapper])],	[], [enable_wsgi_python_egg_cache=auto])
AC_ARG_ENABLE([runtime_dependencies],	[AS_HELP_STRING([--disable-runtime-dependencies],		[Don't enforce runtime dependencies])],         [], [enable_runtime_dependencies=yes])

AC_ARG_VAR([RCYNIC_DIR],		[Where to put output files from rcynic and rpki-rtr])
AC_ARG_VAR([APACHE_VERSION],		[Version of Apache httpd, mostly used on FreeBSD where it determines some of the directory names])

# Obsolete options.  If you know of a better way to handle this, tell me.

AC_ARG_ENABLE([python],		[AS_HELP_STRING([--disable-python],	[(Obsolete, do not use)])], [AC_MSG_ERROR([--disable-python is obsolete.  Please see the --disable-ca-tools option])], [])
AC_ARG_ENABLE([django],		[AS_HELP_STRING([--disable-django],	[(Obsolete, do not use)])], [AC_MSG_ERROR([--disable-django is obsolete.  Please see the --disable-ca-tools option])], [])
AC_ARG_ENABLE([rpki_rtr],	[AS_HELP_STRING([--disable-rpki-rtr],	[(Obsolete, do not use)])], [AC_MSG_ERROR([--disable-rpki-rtr is obsolete.  Please see the --disable-rp-tools option])], [])
AC_ARG_ENABLE([rcynic_jail],	[AS_HELP_STRING([--enable-rcynic-jail],	[(Obsolete, do not use)])], [AC_MSG_ERROR([--enable-rcynic-jail is obsolete.])], [])

AC_PROG_CC
AC_PROG_INSTALL

AC_CHECK_SIZEOF([long])

AC_MSG_CHECKING([whether compiler and linker support -Wl,-Bsymbolic])
old_LDFLAGS="$LDFLAGS"
LDFLAGS="$LDFLAGS -Wl,-Bsymbolic"
AC_LINK_IFELSE([AC_LANG_SOURCE([[int main (int argc, char *argv[]) { return 0; }]])],
	       [linker_supports_Bsymbolic=yes],
	       [linker_supports_Bsymbolic=no])
AC_MSG_RESULT([$linker_supports_Bsymbolic])
LDFLAGS="$old_LDFLAGS"
unset old_LDFLAGS
if test $linker_supports_Bsymbolic = yes
then
	POW_LDFLAGS='-Wl,-Bsymbolic'
else
	POW_LDFLAGS=''
fi
AC_SUBST(POW_LDFLAGS)

AC_MSG_CHECKING([whether compiler and linker support -Wl,-z,noexecstack])
old_LDFLAGS="$LDFLAGS"
LDFLAGS="$LDFLAGS -Wl,-z,noexecstack"
AC_LINK_IFELSE([AC_LANG_SOURCE([[int main (int argc, char *argv[]) { return 0; }]])],
	       [linker_supports_znoexecstack=yes],
	       [linker_supports_znoexecstack=no])
AC_MSG_RESULT([$linker_supports_znoexecstack])
if test $linker_supports_znoexecstack = no
then
	LDFLAGS="$old_LDFLAGS"
fi
unset old_LDFLAGS

AC_PROG_GREP
AC_PATH_PROG([PYTHON], [python])
AC_PATH_PROG([XSLTPROC], [xsltproc])
AC_PATH_PROG([AWK], [awk])
AC_PATH_PROG([SORT], [sort])
AC_PATH_PROG([RRDTOOL], [rrdtool])
AC_PATH_PROG([TRANG], [trang], [\${abs_top_srcdir}/buildtools/trang-not-found])
AC_PATH_PROG([RSYNC], [rsync])
AC_PATH_PROG([SUDO], [sudo])

# See whether we need to check for dependencies that we only need at
# runtime.  We do this by default when compiling from source to avoid
# surprises after installation, but this just adds pain when building
# binary packages within a platform framework which already handles
# all the dependencies for us, so we need a way to turn it off.

case $enable_runtime_dependencies in
	yes|no)
		;;
	*)
		AC_MSG_ERROR([Unrecognized value for --enable-runtime-dependencies: $enable_runtime_dependencies])
		;;
esac

# Figure out whether we want RP tools, CA tools, or both

AC_MSG_CHECKING([whether user wants the RP tools])
case $enable_rp_tools in
     yes|no)
		build_rp_tools=$enable_rp_tools
		;;
     *)
		AC_MSG_ERROR([Unrecognized value for --enable-rp-tools: $enable_rp_tools])
		;;
esac
AC_MSG_RESULT([$build_rp_tools])

AC_MSG_CHECKING([whether user wants the CA tools])
case $enable_ca_tools in
     yes|no)
		build_ca_tools=$enable_ca_tools
		;;
     *)
		AC_MSG_ERROR([Unrecognized value for --enable-ca-tools: $enable_ca_tools])
		;;
esac
AC_MSG_RESULT([$build_ca_tools])

if test $build_rp_tools = no && test $build_ca_tools = no
then
	AC_MSG_ERROR([Building with neither RP tools nor CA tools makes no sense])
fi

# Figure out whether we need to build our own OpenSSL library or can
# use the system libraries.  We're looking for two recent features:
# CMS and RFC 3779 support.  We also have to check whether the user
# has an opinion on all this.  In the "auto" case (no
# --with-system-openssl option specified in any form), we may need to
# check a platform-specific location (eg, /usr/local on FreeBSD).
#
# At this point all of the C code is in the RP tools package, so we can
# skip all this if we're just building the CA tools.

if test $build_rp_tools = no
then

	build_openssl=no

else

	old_CFLAGS="$CFLAGS"
	old_LDFLAGS="$LDFLAGS"

	case $with_system_openssl in
		yes|auto)
			if test $CFLAGS_or_LDFLAGS_were_set = no
			then
				case $host_os in
				freebsd*)
					CFLAGS="-I/usr/local/include $CFLAGS"
					LDFLAGS="-L/usr/local/lib $LDFLAGS"
					;;
				esac
			fi
			;;
		no|/usr)
			:
			;;

		*)
			CFLAGS="-I$with_system_openssl/include $CFLAGS"
			LDFLAGS="-L$with_system_openssl/lib $LDFLAGS"
	esac

	case $with_system_openssl in
		no)
			have_usable_openssl=no
			;;
		*)
			AC_CHECK_LIB([crypto], [X509v3_addr_validate_path],
					       [system_openssl_has_rfc3779=yes],
					       [system_openssl_has_rfc3779=no])

			AC_CHECK_LIB([crypto], [CMS_verify],
					       [system_openssl_has_cms=yes],
					       [system_openssl_has_cms=no])

			AC_MSG_CHECKING([whether system OpenSSL library is usable])
			if test $system_openssl_has_rfc3779 = yes && test $system_openssl_has_cms = yes
			then
				have_usable_openssl=yes
			else
				have_usable_openssl=no
			fi
			AC_MSG_RESULT([$have_usable_openssl])
	esac

	AC_MSG_CHECKING([whether we need to build a private copy of OpenSSL])
	case $with_system_openssl in
	     yes)
			build_openssl=no
			if test $have_usable_openssl = no
			then
				AC_MSG_ERROR([Can't find OpenSSL crypto library with CMS and RFC 3779 support, try --with-system-openssl=/path/to/openssl])
			fi
			;;
	     no)
			build_openssl=yes
			;;
	     auto)
			if test $have_usable_openssl = no
			then
				build_openssl=yes
			else
				build_openssl=no
			fi
			;;
	     *)
			build_openssl=no
			if test $have_usable_openssl = no
			then
				AC_MSG_ERROR([Can't find OpenSSL crypto library with CMS and RFC 3779 support in $with_system_openssl])
			fi
	esac
	AC_MSG_RESULT([$build_openssl])

	build_openssl_asm=undefined

	if test $build_openssl = yes
	then
		CFLAGS="$old_CFLAGS"
		LDFLAGS="$old_LDFLAGS"

		AC_MSG_CHECKING([whether to enable assembly code in OpenSSL])
		case $enable_openssl_asm in
		     yes|no)
				build_openssl_asm=$enable_openssl_asm
				;;
		     auto)
				case $host in
					x86_64-*-linux*)
						build_openssl_asm=no
						;;
					*)
						build_openssl_asm=yes
						;;
				esac
				;;
		     *)
				AC_MSG_ERROR([Unrecognized value for --enable-openssl-asm: $enable_openssl_asm])
				;;
		esac     
		AC_MSG_RESULT([$enable_openssl_asm])
	fi
fi

# RCYNIC_DIR is a "precious" argument variable to this script (see
# autoconf doc), which means that autoconf is careful with whatever
# value (if any) was passed in, and that it's already been declared
# for variable substitution.  We still have to set a default value for
# it, though, and we might as well handle DESTDIR while we're at it.

if test "X$RCYNIC_DIR" = "X"
then
	RCYNIC_DIR='/var/rcynic'
fi

# APACHE_VERSION is another "precious" argument to this script.  It
# mostly matters on FreeBSD, where most things involving Apache encode
# the Apache version number into their filenames.
#
# If we can't figure out the version number, we assume 2.4 and hope
# for the best; at some point we may need to do better than this.
#
# apachectl sometimes whines about ulimits, so we discard its stderr.
# If you're reading this because this test is misbehaving, well,
# try not discarding stderr.

AC_MSG_CHECKING([Apache version])

if test "X$APACHE_VERSION" = "X"
then
	for apachectl in /usr/local/sbin/apachectl /usr/sbin/apachectl
	do
		if test -x $apachectl
		then
			APACHE_VERSION=`$apachectl -v 2>/dev/null | sed -n 's=^Server version: Apache/\([[0-9]]*\)\.\([[0-9]]*\)\..*$=\1\2=p'`
			break
		fi
	done
fi

if test "X$APACHE_VERSION" = "X"
then
	APACHE_VERSION="24"
	msg='not found, defaulting to 2.4'
else
	msg=`echo $APACHE_VERSION | sed 's=.=&.='`
fi

AC_MSG_RESULT([$msg])

# Perhaps there should be a way to set these, but for now just
# wire them in here so at least they're consistent in all Makefiles.

AC_SUBST(RPKI_USER,    [rpki])
AC_SUBST(RPKI_GROUP,   [rpki])

RCYNIC_CONF_DATA="${RCYNIC_DIR}/data"

AC_SUBST(RCYNIC_CONF_DATA)

# Check whether to do "final target installation".  This means actions
# that can only be done when installing a package, as opposed to when
# building a package.

AC_MSG_CHECKING([whether to do final target installation on "make install"])

case $enable_target_installation in
	yes|no)
		;;
	*)
		AC_MSG_ERROR([Unrecognized value for --enable-target-installation: $enable_target_installation])
		;;
esac

AC_MSG_RESULT([$enable_target_installation])

# Some bits of post-installation setup are complicated enough that
# it's simplest to have different rule sets for different platforms.

case $host_os in
	darwin*)
		RCYNIC_MAKE_RULES='rp/rcynic/rules.darwin.mk'
		RTR_ORIGIN_MAKE_RULES='rp/rpki-rtr/rules.darwin.mk'
		CA_MAKE_RULES='ca/rules.darwin.mk'
		;;
	freebsd*)
		RCYNIC_MAKE_RULES='rp/rcynic/rules.freebsd.mk'
		RTR_ORIGIN_MAKE_RULES='rp/rpki-rtr/rules.freebsd.mk'
		CA_MAKE_RULES='ca/rules.freebsd.mk'
		;;
	linux*)
		RCYNIC_MAKE_RULES='rp/rcynic/rules.linux.mk'
		RTR_ORIGIN_MAKE_RULES='rp/rpki-rtr/rules.linux.mk'
		CA_MAKE_RULES='ca/rules.linux.mk'
		;;
	*)
		RCYNIC_MAKE_RULES='rp/rcynic/rules.unknown.mk'
		RTR_ORIGIN_MAKE_RULES='rp/rpki-rtr/rules.unknown.mk'
		CA_MAKE_RULES='ca/rules.unknown.mk'
		;;
esac

AC_SUBST_FILE(RCYNIC_MAKE_RULES)
AC_SUBST_FILE(RTR_ORIGIN_MAKE_RULES)
AC_SUBST_FILE(CA_MAKE_RULES)

# Where to put HTML files is similarly platform dependent, we have to know.
# rcynic-cron will skip generating HTML files if it has no place to put them.

AC_MSG_CHECKING([where rcynic-html output should go])
case $host_os in
	freebsd*)
		RCYNIC_HTML_DIR="/usr/local/www/apache${APACHE_VERSION}/data/rcynic"
		;;
	linux*)
		RCYNIC_HTML_DIR='/var/www/html/rcynic'
		;;
	*)
		RCYNIC_HTML_DIR=''
		;;
esac
AC_MSG_RESULT([$RCYNIC_HTML_DIR])

AC_SUBST(RCYNIC_HTML_DIR)

# Sort out which things to install, depending on whether
# we're doing final target installation.
#
# As things have evolved, this a bit repetitive.  Simplify someday, maybe.

RCYNIC_INSTALL_TARGETS='install-always'
RTR_ORIGIN_INSTALL_TARGETS='install-always'
CA_INSTALL_TARGETS='install-always'
CFG_INSTALL_TARGETS='install-always'

if test $enable_target_installation = yes
then
	RCYNIC_INSTALL_TARGETS="$RCYNIC_INSTALL_TARGETS install-postconf"
	RTR_ORIGIN_INSTALL_TARGETS="$RTR_ORIGIN_INSTALL_TARGETS install-postconf"
	CA_INSTALL_TARGETS="$CA_INSTALL_TARGETS install-postconf"
	CFG_INSTALL_TARGETS="$CFG_INSTALL_TARGETS install-postconf"
fi

AC_SUBST(RCYNIC_INSTALL_TARGETS)
AC_SUBST(RTR_ORIGIN_INSTALL_TARGETS)
AC_SUBST(CA_INSTALL_TARGETS)
AC_SUBST(CFG_INSTALL_TARGETS)

# Now a bunch of checks to figure out what we can do with Python.  If
# we don't have Python at all, none of the rest of this matters.  If
# we do have Python, we need to check for required packages and
# versions.

if test "x$PYTHON" = "x"
then
	AC_MSG_ERROR([I can't find a Python binary at all, this isn't going to work.  Perhaps you need to set PATH?])
fi

AC_MSG_CHECKING([for Python version 2.7 or higher])
have_acceptable_python=`$PYTHON -c 'import sys; print "yes" if sys.version_info[[0]] == 2 and sys.version_info[[1]] >= 7 else "no"'`
AC_MSG_RESULT([$have_acceptable_python])

AC_MSG_CHECKING([distutils to find out where Python.h should be])
python_h=`$PYTHON -c 'import distutils.sysconfig; print distutils.sysconfig.get_python_inc() + "/Python.h"'`
AC_MSG_RESULT([$python_h])

AC_CHECK_HEADER([$python_h], [have_python_h=yes], [have_python_h=no])

AC_MSG_CHECKING([for lxml.etree])
if $PYTHON -c 'import lxml.etree' 2>/dev/null; then have_lxml=yes; else have_lxml=no; fi
AC_MSG_RESULT([$have_lxml])

AC_MSG_CHECKING([for Tornado])
if $PYTHON -c 'import tornado' 2>/dev/null; then have_tornado=yes; else have_tornado=no; fi
AC_MSG_RESULT([$have_tornado])

if test $have_tornado = yes
then
	AC_MSG_CHECKING([for Tornado 4.2 or higher])
	have_acceptable_tornado=`$PYTHON -c "import tornado; print 'no' if tornado.version_info < (4, 2) else 'yes'"`
	AC_MSG_RESULT([$have_acceptable_tornado])
else
	have_acceptable_tornado=no
fi

AC_MSG_CHECKING([for Django])
if $PYTHON -c 'import django' 2>/dev/null; then have_django=yes; else have_django=no; fi
AC_MSG_RESULT([$have_django])

if test $have_django = yes
then
	AC_MSG_CHECKING([for Django 1.8 or higher])
	have_acceptable_django=`$PYTHON -c "import django; print 'no' if django.VERSION < (1, 8) else 'yes'"`
	AC_MSG_RESULT([$have_acceptable_django])
else
	have_acceptable_django=no
fi

AC_MSG_CHECKING([for PyYAML])
if $PYTHON -c 'import yaml' 2>/dev/null; then have_pyyaml=yes; else have_pyyaml=no; fi
AC_MSG_RESULT([$have_pyyaml])

AC_MSG_CHECKING([for vobject])
if $PYTHON -c 'import vobject' 2>/dev/null; then have_vobject=yes; else have_vobject=no; fi
AC_MSG_RESULT([$have_vobject])

AC_MSG_CHECKING([for argparse])
if $PYTHON -c 'import argparse' 2>/dev/null; then have_argparse=yes; else have_argparse=no; fi
AC_MSG_RESULT([$have_argparse])

# Warnings and dependency errors.  Exit on fatal errors deferred until
# the very end of this, so we can warn the user about all known
# problems in a single pass.  Errors that prevent build or basic
# installation are always fatal; errors that prevent proper operation
# at runtime or during post-installation setup can be converted to
# warnings by --disable-runtime-dependencies.

build_ok=yes
runtime_ok=yes

if test $have_acceptable_python = no
then
	runtime_ok=no
	AC_MSG_WARN([The RPKI code requires Python version 2.x, for x = 7 or higher.])
fi

if test $build_rp_tools = yes
then
	if test $have_python_h = no
	then
		build_ok=no
		AC_MSG_WARN([I can't find Python.h.  Python sources are required to build the rpki.POW module.])
	fi
	if test "x$RRDTOOL" = "x"
	then
		runtime_ok=no
		AC_MSG_WARN([rcynic-html requires rrdtool.])
	fi
	if test "X$RSYNC" = "X"
	then
		runtime_ok=no
		AC_MSG_WARN([The RPKI relying party tools require rsync.])
	fi
fi

if test $have_lxml = no
then
	runtime_ok=no
	AC_MSG_WARN([The RPKI tools require the Python LXML package.])
fi

if test $have_acceptable_django = no
then
	runtime_ok=no
	AC_MSG_WARN([The RPKI tools require Django 1.8 or higher.])
fi

if test $have_argparse = no
then
	runtime_ok=no
	AC_MSG_WARN([The RPKI tools require the Python argparse module.])
fi

if test $have_acceptable_tornado = no
then
	runtime_ok=no
	AC_MSG_WARN([The RPKI tools require Tornado 4.2 or higher.])
fi

if test $build_ca_tools = yes
then
	if test $have_vobject = no
	then
		runtime_ok=no
		AC_MSG_WARN([The RPKI CA GUI requires the Python vobject module.])
	fi
	if test $have_pyyaml = no
	then
		AC_MSG_WARN([PyYAML missing, so "make test" will not work properly.])
	fi
	if test "x$XSLTPROC" = "x"
	then
		AC_MSG_WARN([xsltproc missing, so "make test" will not work properly.])
	fi
fi

if test $build_ok = no || test $runtime_ok = no
then
	if test $build_rp_tools = yes
	then
		AC_MSG_WARN([If you do not wish to install the RPKI RP tools, please specify --disable-rp-tools as an argument to this configure script.])
	fi
	if test $build_ca_tools = yes
	then
		AC_MSG_WARN([If you do not wish to install the RPKI CA tools, please specify --disable-ca-tools as an argument to this configure script.])
	fi
	if test $build_ok = no || test $enable_runtime_dependencies = yes
	then
		AC_MSG_ERROR([Please correct the problems above then re-run this configuration script.])
	else
		AC_MSG_WARN([Runtime dependency enforcement disabled, proceeding (at your own risk)])
	fi
fi

# Figure out whether we are on a Debian-derived system where we need
# to tell setup.py about Debian installation layout.

if test $build_ca_tools = yes
then
	AC_MSG_CHECKING([whether we need to tell distutils to use a particular installation layout])
	looks_like_debian=no
	if test -x /usr/bin/lsb_release
	then
		case `/usr/bin/lsb_release -is` in
		Debian|Ubuntu)
			looks_like_debian=yes
			;;
		esac
	fi
	if test $looks_like_debian = yes
	then
		install_layout="deb"
	else
		install_layout="unix"
	fi
	case $enable_python_install_layout in
	yes|no)
		use_install_layout=$enable_python_install_layout
		;;
	auto)
		use_install_layout=no
		;;
	*)
		use_install_layout=yes
		install_layout="$enable_python_install_layout"
		;;
	esac
	if test $use_install_layout = yes
	then
		SETUP_PY_INSTALL_LAYOUT="--install-layout=$install_layout"
	else
		SETUP_PY_INSTALL_LAYOUT=''

	fi
	AC_MSG_RESULT([$use_install_layout $SETUP_PY_INSTALL_LAYOUT])
	AC_SUBST(SETUP_PY_INSTALL_LAYOUT)
fi

# Figure out whether we're going to want a PYTHON_EGG_CACHE directory.
# This is mostly just a pass through to rpkigui-apache-confgen and rpki.wsgi
# via rpki.autoconf.

AC_MSG_CHECKING([whether we need rpki.wgi to use a Python egg cache])

save_IFS="$IFS"
IFS=':' read WSGI_PYTHON_EGG_CACHE_DIR WSGI_PYTHON_EGG_CACHE_USER <<_EOF
$enable_wsgi_python_egg_cache
_EOF
IFS="$save_IFS"

if test "X$WSGI_PYTHON_EGG_CACHE_DIR" = "Xauto"
then
	case $host_os in
	freebsd*)	WSGI_PYTHON_EGG_CACHE_DIR=yes;;
	*)		WSGI_PYTHON_EGG_CACHE_DIR=no;;
	esac
fi

case $WSGI_PYTHON_EGG_CACHE_DIR in
yes)
	WSGI_PYTHON_EGG_CACHE_DIR='${datarootdir}/rpki/python-eggs'
	;;
no)
	WSGI_PYTHON_EGG_CACHE_DIR=''
	;;
esac

if test "X$WSGI_PYTHON_EGG_CACHE_DIR" != "X" &&
   test "X$WSGI_PYTHON_EGG_CACHE_USER" = "X"
then
	case $host_os in
	freebsd*)	WSGI_PYTHON_EGG_CACHE_USER="www";;
	linux*)		WSGI_PYTHON_EGG_CACHE_USER="www-data";;
	esac
fi

AC_SUBST(WSGI_PYTHON_EGG_CACHE_DIR)
AC_SUBST(WSGI_PYTHON_EGG_CACHE_USER)

if test "X$WSGI_PYTHON_EGG_CACHE_DIR" = "X"
then
	AC_MSG_RESULT([no])
elif test "X$WSGI_PYTHON_EGG_CACHE_USER" != "X"
then
	AC_MSG_RESULT([$WSGI_PYTHON_EGG_CACHE_DIR (user $WSGI_PYTHON_EGG_CACHE_USER)])
else
	AC_MSG_RESULT([$WSGI_PYTHON_EGG_CACHE_DIR])
fi

# Tell the Makefiles and setup.py which parts of this package we've decided to build.

if test $build_openssl  = yes; then OPENSSL_TARGET=openssl; else OPENSSL_TARGET=noop; fi
if test $build_rp_tools = yes; then      RP_TARGET=rp;	    else      RP_TARGET=noop; fi
if test $build_ca_tools = yes; then      CA_TARGET=ca;	    else      CA_TARGET=noop; fi

AC_SUBST(OPENSSL_TARGET)
AC_SUBST(RP_TARGET)
AC_SUBST(CA_TARGET)

AC_CONFIG_FILES([Makefile])

# OpenSSL has its own build system that bears no relationship to
# anything but itself, and our use of it is a bit weird, so this is a
# BFMI (Brute Force and Massive Ignorance) job.

if test $build_openssl = yes
then
	AC_CONFIG_FILES([openssl/Makefile
			 openssl/tests/Makefile])

	AC_MSG_CHECKING([what configuration target to use when building OpenSSL])
	case $host in
	i*86-apple-darwin*)
		if test "$ac_cv_sizeof_long" = 8
		then
			OPENSSL_CONFIG_COMMAND='./Configure darwin64-x86_64-cc'
		fi
		;;
	*)
		if test $build_openssl_asm = yes
		then
			OPENSSL_CONFIG_COMMAND="MACHINE=$host_cpu ./config"
		else
			OPENSSL_CONFIG_COMMAND="MACHINE=$host_cpu ./config no-asm"
		fi
		;;
	esac
	AC_SUBST(OPENSSL_CONFIG_COMMAND)
	AC_MSG_RESULT([$OPENSSL_CONFIG_COMMAND])

	AC_MSG_CHECKING([what glob to use when renaming OpenSSL shared libraries])
	case $host in
	*-apple-darwin*)
		OPENSSL_SO_GLOB='*.dylib'
		;;
	*)
		OPENSSL_SO_GLOB='*.so*'
		;;
	esac
	AC_SUBST(OPENSSL_SO_GLOB)
	AC_MSG_RESULT([$OPENSSL_SO_GLOB])

	# NB: We put our OpenSSL directory at the *front* of the
	# search list to preempt conflicts with system copies.

	CFLAGS="-I\${abs_top_srcdir}/openssl/openssl/include $CFLAGS"
	LIBS="\${abs_top_builddir}/openssl/openssl/libcrypto.a $LIBS"
else
	LIBS="$LIBS -lcrypto"
fi

if test $build_rp_tools = yes
then
	AC_CONFIG_FILES([rp/Makefile
			 rp/config/Makefile
			 rp/rcynic/Makefile
			 rp/utils/Makefile
			 rp/rpki-rtr/Makefile])
fi

if test $build_ca_tools = yes
then
	AC_CONFIG_FILES([ca/Makefile
			 ca/tests/Makefile])
fi

if test $build_ca_tools = yes
then
	case $enable_wsgi_daemon_mode in
	no)
		;;
	yes)
		AC_MSG_ERROR([You must specify the user to run the wsgi process as with --enable-wsgi-daemon-mode=USER])
		;;
	*)
		AC_MSG_CHECKING([how to run mod_wsgi daemon mode])
		save_IFS="$IFS"
		IFS=':'
		read user group <<_EOF
$enable_wsgi_daemon_mode
_EOF
		IFS="$save_IFS"
		AC_SUBST(WSGI_DAEMON_PROCESS, "WSGIDaemonProcess rpkigui user=$user ${group:+group=}${group} display-name=%{GROUP}")
		AC_SUBST(WSGI_PROCESS_GROUP, "WSGIProcessGroup rpkigui")
		AC_MSG_RESULT([with user "$user" and group "${group:-default}"])
		;;
	esac
fi

# Now that we're finally done with all the conditional changes to
# CFLAGS, add a search directive for our own header directory.  If we
# ever get to the point of having our own library directory, we'd add
# it here too, but for the moment our shared C code is all in .h files.

CFLAGS="$CFLAGS -I\${abs_top_srcdir}/h"

AC_OUTPUT
