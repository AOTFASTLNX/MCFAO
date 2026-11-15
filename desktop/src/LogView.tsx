import { logLevel, logTone } from "./log";

export function LogView({
  text,
  label,
  className = "",
}: {
  text: string;
  label: string;
  className?: string;
}) {
  const lines = text ? text.split(/\r?\n/) : [];
  return (
    <pre className={"log-output " + className} aria-label={label}>
      {lines.length
        ? lines.map((line, index) => {
            const tone = logTone(line);
            const level = logLevel(line);
            return (
              <span className={"log-line " + tone} key={index}>
                {level && <span className="log-level">{level}</span>}
                {line}
              </span>
            );
          })
        : "等待构建输出。后台任务正在保存日志。"}
    </pre>
  );
}
