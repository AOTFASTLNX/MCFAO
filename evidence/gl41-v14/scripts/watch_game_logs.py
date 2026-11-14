import asyncio, pathlib, re
from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.house_arrest import HouseArrestService

out = pathlib.Path(__file__).with_name("live-game-logs")
out.mkdir(exist_ok=True)
directory = "/Documents/c0-logs"
async def main():
    while True:
        try:
            async with await asyncio.wait_for(create_using_usbmux(connection_type="USB", autopair=False), 10) as phone:
                async with await asyncio.wait_for(HouseArrestService.create(phone, "app.perseus4004.sunset349", documents_only=True), 10) as afc:
                    names = await asyncio.wait_for(afc.listdir(directory), 10)
                    for name in sorted(n for n in names if re.fullmatch(r"run-[0-9]+\.log", n))[-2:]:
                        content = await asyncio.wait_for(afc.get_file_contents(f"{directory}/{name}"), 10)
                        target = out / name
                        if not target.exists() or len(content) > target.stat().st_size:
                            part = target.with_suffix(".part")
                            part.write_bytes(content)
                            part.replace(target)
        except Exception as exc:
            print(type(exc).__name__, flush=True)
        await asyncio.sleep(10)
asyncio.run(main())
