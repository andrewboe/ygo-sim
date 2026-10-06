-- Replacement for ygo-agent's repo/packages/e/edopro-core/xmake.lua.
-- The core is prebuilt by ygo-sim/wsl/build_core.sh (meson; Lua compiled as C++);
-- this package only installs its static libs and headers.
package("edopro-core")
    set_homepage("https://github.com/edo9300/ygopro-core")
    set_sourcedir(path.join(os.getenv("HOME"), "ygo/edopro-core"))

    on_load(function (package)
        package:add("links", "ocgcore", "lua")
    end)

    on_install("linux", function (package)
        os.cp("*.h", package:installdir("include", "edopro-core"))
        os.cp("RNG", package:installdir("include", "edopro-core"))
        os.cp("lua/src/*.h", package:installdir("include"))
        os.cp("build/libocgcore.a", package:installdir("lib"))
        os.cp("build/lua/liblua.a", package:installdir("lib"))
    end)
package_end()
