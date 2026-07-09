import asyncio
from dataclasses import dataclass
from typing import Any

import aiohttp

from config import settings


class RewriteError(Exception):
    """Ошибка взаимодействия с API рерайта."""


@dataclass
class RewriteTask:
    task_id: str
    provider: str
    service_name: str = "rewriting"
    immediate_result: str | None = None


class TextRuRewriteClient:
    """
    Клиент для Text.ru Neuro Rewriting API.

    Поддерживает несколько вариантов endpoint-ов/форматов, потому что разные
    тарифы API могут использовать немного отличающиеся схемы авторизации.
    """

    def __init__(self, api_key: str):
        self.api_key = (api_key or "").strip()
        if not self.api_key:
            raise RewriteError("Не задан TEXT_API_KEY в .env")

    @staticmethod
    def _extract_balance_units(payload: dict[str, Any]) -> int | None:
        candidates = [
            payload.get("neuroSymbols"),
            payload.get("neurosymbols"),
            payload.get("balance"),
            payload.get("symbols"),
            payload.get("available"),
            payload.get("available_symbols"),
            (payload.get("data") or {}).get("neuroSymbols") if isinstance(payload.get("data"), dict) else None,
            (payload.get("data") or {}).get("balance") if isinstance(payload.get("data"), dict) else None,
            (payload.get("data") or {}).get("symbols") if isinstance(payload.get("data"), dict) else None,
            (payload.get("data") or {}).get("available") if isinstance(payload.get("data"), dict) else None,
        ]
        for value in candidates:
            if value is None:
                continue
            try:
                return int(float(str(value).replace(",", ".").strip()))
            except (TypeError, ValueError):
                continue
        return None

    @staticmethod
    def _extract_api_error(payload: dict[str, Any]) -> str | None:
        error_desc = payload.get("error_desc") or payload.get("error") or payload.get("message")
        error_code = payload.get("error_code")
        if error_desc and error_code is not None:
            return f"[{error_code}] {error_desc}"
        if error_desc:
            return str(error_desc)
        return None

    @staticmethod
    def _is_ok_status(raw_status: Any) -> bool:
        if raw_status is None:
            return False
        status = str(raw_status).strip().lower()
        return status in {"ready", "completed", "done", "success", "ok"}

    @staticmethod
    def _is_fail_status(raw_status: Any) -> bool:
        if raw_status is None:
            return False
        status = str(raw_status).strip().lower()
        return status in {"failed", "error", "cancelled"}

    @staticmethod
    def _extract_result_text(payload: dict[str, Any]) -> str | None:
        candidates = [
            payload.get("result"),
            payload.get("text"),
            payload.get("rewritten_text"),
            payload.get("rewrite"),
            (payload.get("result") or {}).get("text") if isinstance(payload.get("result"), dict) else None,
            (payload.get("data") or {}).get("result") if isinstance(payload.get("data"), dict) else None,
            (payload.get("data") or {}).get("text") if isinstance(payload.get("data"), dict) else None,
            (payload.get("data") or {}).get("rewritten_text") if isinstance(payload.get("data"), dict) else None,
        ]
        for value in candidates:
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    @staticmethod
    def _extract_task_id(payload: dict[str, Any]) -> str | None:
        candidates = [
            payload.get("taskId"),
            payload.get("task_id"),
            payload.get("uid"),
            payload.get("text_uid"),
            (payload.get("data") or {}).get("taskId") if isinstance(payload.get("data"), dict) else None,
            (payload.get("data") or {}).get("task_id") if isinstance(payload.get("data"), dict) else None,
            (payload.get("data") or {}).get("uid") if isinstance(payload.get("data"), dict) else None,
        ]
        for value in candidates:
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        return None

    async def _json_request(
        self,
        session: aiohttp.ClientSession,
        method: str,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any] | None = None,
    ) -> tuple[int, dict[str, Any]]:
        kwargs: dict[str, Any] = {"headers": headers}
        if payload is not None:
            kwargs["json"] = payload

        async with session.request(method, url, **kwargs) as response:
            status = response.status
            data: dict[str, Any]
            try:
                data = await response.json(content_type=None)
            except Exception:
                raw = await response.text()
                data = {"error": raw[:500]}
            return status, data

    async def _create_task(
        self,
        session: aiohttp.ClientSession,
        source_text: str,
        creative: int,
    ) -> RewriteTask:
        attempts: list[tuple[str, str, dict[str, str], dict[str, Any]]] = [
            (
                "api.text.ru/neurotools/api/v1/task/rewriting (X-USERKEY)",
                "https://api.text.ru/neurotools/api/v1/task/rewriting",
                {"X-USERKEY": self.api_key, "Content-Type": "application/json", "Accept": "application/json"},
                {"text": source_text, "creative": creative, "language": "ru"},
            ),
            (
                "api.text.ru/neuro/rewriting (Bearer)",
                "https://api.text.ru/neuro/rewriting",
                {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                {"text": source_text, "creative": creative, "language": "ru"},
            ),
            (
                "api.text.ru/neuro/rewriting (X-Api-Key)",
                "https://api.text.ru/neuro/rewriting",
                {"X-Api-Key": self.api_key, "Content-Type": "application/json"},
                {"text": source_text, "creative": creative, "language": "ru"},
            ),
            (
                "api.text.ru/post (userkey+tool)",
                "https://api.text.ru/post",
                {"Content-Type": "application/json"},
                {"userkey": self.api_key, "text": source_text, "tool": "rewriting", "creative": creative, "language": "ru"},
            ),
        ]

        errors: list[str] = []
        for provider, url, headers, payload in attempts:
            status, data = await self._json_request(session, "POST", url, headers, payload)
            if status >= 400:
                errors.append(f"{provider}: HTTP {status}")
                continue

            api_error = self._extract_api_error(data)
            if api_error:
                errors.append(f"{provider}: {api_error}")
                continue

            task_id = self._extract_task_id(data)
            if task_id:
                service_name = str(data.get("serviceName") or "rewriting").strip() or "rewriting"
                return RewriteTask(task_id=task_id, provider=provider, service_name=service_name)

            ready_text = self._extract_result_text(data)
            if ready_text:
                # Редкий случай: API сразу вернул результат, без очереди.
                return RewriteTask(task_id="", provider=provider, immediate_result=ready_text)

            errors.append(f"{provider}: task id не найден в ответе")

        raise RewriteError("Не удалось создать задачу рерайта: " + "; ".join(errors))

    async def _check_balance(self, session: aiohttp.ClientSession):
        """
        Проверяет баланс нейросимволов перед запуском рерайта.
        Требование API: ключ передаётся в заголовке X-USERKEY.
        """
        status, data = await self._json_request(
            session,
            "GET",
            "https://api.text.ru/neurotools/api/v1/balance",
            {"X-USERKEY": self.api_key, "Accept": "application/json"},
        )

        if status == 401:
            raise RewriteError("Ошибка авторизации TEXT.ru: проверьте TEXT_API_KEY (X-USERKEY)")
        if status >= 400:
            raise RewriteError(f"Ошибка проверки баланса TEXT.ru: HTTP {status}")

        api_error = self._extract_api_error(data)
        if api_error:
            raise RewriteError(f"Ошибка проверки баланса TEXT.ru: {api_error}")

        balance = self._extract_balance_units(data)
        if balance is not None and balance <= 0:
            raise RewriteError("Нехватка символов на балансе TEXT.ru")

    async def _get_result_once(
        self,
        session: aiohttp.ClientSession,
        task: RewriteTask,
    ) -> tuple[str | None, bool]:
        # Вернём два флага: (text, is_final)
        candidate_checks: list[tuple[str, str, dict[str, str], dict[str, Any] | None]] = [
            (
                "api.text.ru/neurotools/api/v1/task/{service}/{id}",
                f"https://api.text.ru/neurotools/api/v1/task/{task.service_name}/{task.task_id}",
                {"X-USERKEY": self.api_key, "Accept": "application/json"},
                None,
            ),
            (
                "text.ru/neuro/task",
                f"https://text.ru/neuro/task/{task.task_id}",
                {"Accept": "application/json"},
                None,
            ),
            (
                "api.text.ru/neuro/task (Bearer)",
                f"https://api.text.ru/neuro/task/{task.task_id}",
                {"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"},
                None,
            ),
            (
                "api.text.ru/neuro/task (X-Api-Key)",
                f"https://api.text.ru/neuro/task/{task.task_id}",
                {"X-Api-Key": self.api_key, "Accept": "application/json"},
                None,
            ),
            (
                "api.text.ru/post uid",
                "https://api.text.ru/post",
                {"Content-Type": "application/json"},
                {"userkey": self.api_key, "uid": task.task_id},
            ),
        ]

        for _, url, headers, payload in candidate_checks:
            method = "GET" if payload is None else "POST"
            status, data = await self._json_request(session, method, url, headers, payload)
            if status >= 400:
                continue

            text = self._extract_result_text(data)
            if text:
                return text, True

            raw_status = data.get("status")
            if self._is_ok_status(raw_status):
                final_text = self._extract_result_text(data)
                if final_text:
                    return final_text, True
                return None, True

            if self._is_fail_status(raw_status):
                error = data.get("error") or data.get("message") or "неизвестная ошибка API"
                raise RewriteError(f"Сервис рерайта вернул ошибку: {error}")

            # Если статус "processing/queued" или отсутствует, продолжаем polling.
        return None, False

    async def rewrite_text(
        self,
        source_text: str,
        creative: int = 5,
        timeout_sec: int = 120,
        poll_interval_sec: int = 4,
    ) -> str:
        text = (source_text or "").strip()
        if not text:
            raise RewriteError("Пустой исходный текст для рерайта")

        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            await self._check_balance(session)
            task = await self._create_task(session, text, creative)

            if task.immediate_result:
                return task.immediate_result
            if not task.task_id:
                raise RewriteError("Задача рерайта создана без task_id")

            deadline = asyncio.get_running_loop().time() + timeout_sec
            while asyncio.get_running_loop().time() < deadline:
                result_text, final = await self._get_result_once(session, task)
                if result_text:
                    return result_text
                if final:
                    break
                await asyncio.sleep(poll_interval_sec)

        raise RewriteError("Таймаут ожидания результата рерайта")


async def rewrite_text_via_text_ru(source_text: str, creative: int = 5) -> str:
    client = TextRuRewriteClient(api_key=settings.text_api_key)
    return await client.rewrite_text(source_text=source_text, creative=creative)
