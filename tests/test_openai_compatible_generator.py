import json
import unittest
from unittest.mock import patch
import httpx
from backend.openai_compatible_generator import OpenAICompatibleGenerator, validated_chat_endpoint
from backend.generation import ProviderUnavailableError, ProviderResponseError, ProviderTimeoutError, ProviderRateLimitError, ProviderCompletionExhaustedError
from backend.settings import GenerationSettings
from backend.schemas import ChatRequest

class OpenAICompatibleUrlTests(unittest.TestCase):
    def settings(self, url, hosts=("example.test",)):
        return GenerationSettings("openai_compatible", None, "model", 30, 2048, url, hosts)
    def test_allowlisted_https_endpoint(self):
        self.assertEqual(validated_chat_endpoint(self.settings("https://example.test/v1")), "https://example.test/v1/chat/completions")
    def test_loopback_http_only(self):
        self.assertEqual(validated_chat_endpoint(self.settings("http://localhost/v1", ("localhost",))), "http://localhost/v1/chat/completions")
        with self.assertRaises(ProviderUnavailableError): validated_chat_endpoint(self.settings("http://example.test/v1"))
    def test_allowlisted_ipv4_loopback_http_endpoint(self):
        self.assertEqual(validated_chat_endpoint(self.settings("http://127.0.0.1/v1", ("127.0.0.1",))), "http://127.0.0.1/v1/chat/completions")
    def test_allowlisted_ipv6_loopback_http_endpoint(self):
        self.assertEqual(validated_chat_endpoint(self.settings("http://[::1]/v1", ("::1",))), "http://[::1]/v1/chat/completions")
    def test_missing_or_wildcard_allowlist_is_rejected(self):
        with self.assertRaises(ProviderUnavailableError): validated_chat_endpoint(self.settings("https://example.test/v1", ()))
        with self.assertRaises(ProviderUnavailableError): validated_chat_endpoint(self.settings("https://example.test/v1", ("*.test",)))
    def test_fixed_endpoint_preserves_v1_and_trailing_slash(self):
        self.assertEqual(validated_chat_endpoint(self.settings("https://example.test/v1/")), "https://example.test/v1/chat/completions")
    def test_rejects_unsafe_url_forms(self):
        for url in ("https://user@example.test/v1", "https://example.test/v1?q=x", "https://example.test/v1#x", "https://other.test/v1"):
            with self.subTest(url=url), self.assertRaises(ProviderUnavailableError): validated_chat_endpoint(self.settings(url))
    def test_rejects_scheme_relative_unsupported_control_and_malformed_port(self):
        for url in ("//example.test/v1", "ftp://example.test/v1", "https://example.test:99999/v1", "https://example.test/\n"):
            with self.subTest(url=url), self.assertRaises(ProviderUnavailableError): validated_chat_endpoint(self.settings(url))

    def test_rejects_all_userinfo_and_authority_ambiguity(self):
        cases = (
            "https://user@example.test", "https://user:password@example.test",
            "https://:password@example.test", "https://user%40name@example.test",
            "https://user:pass%40word@example.test", "https://first@second@example.test",
            "https://%40example.test", "https://\\example.test", "https://example.test\\path",
            "https://example.test/\\path", "https:\\\\example.test", "https://",
            "//example.test", "https://https://example.test",
        )
        for url in cases:
            with self.subTest(url=url), self.assertRaises(ProviderUnavailableError):
                validated_chat_endpoint(self.settings(url))

    def test_rejects_whitespace_controls_and_malformed_ports(self):
        controls = ("\r", "\n", "\t", "\x00", "\x01", "\x7f", "\u2028", "\u2029", "\u00a0")
        for value in controls:
            for url in (f"https://example.test/{value}", f"{value}https://example.test", f"https://example.test{value}"):
                with self.subTest(value=repr(value), url=repr(url)), self.assertRaises(ProviderUnavailableError):
                    validated_chat_endpoint(self.settings(url))
        for url in ("https://[::1", "https://::1]", "https://[bad]", "https://example.test:bad", "https://example.test:0", "https://example.test:65536"):
            with self.subTest(url=url), self.assertRaises(ProviderUnavailableError):
                validated_chat_endpoint(self.settings(url))
        self.assertEqual(validated_chat_endpoint(self.settings("https://example.test:1", ("example.test",))), "https://example.test:1/chat/completions")
        self.assertEqual(validated_chat_endpoint(self.settings("https://example.test:65535", ("example.test",))), "https://example.test:65535/chat/completions")

    def test_host_allowlist_is_exact_and_normalized_only_for_case(self):
        self.assertEqual(validated_chat_endpoint(self.settings("https://EXAMPLE.TEST", ("example.test",))), "https://example.test/chat/completions")
        rejected = (
            ("https://approved.example.evil.test", ("approved.example",)),
            ("https://evil-approved.example", ("approved.example",)),
            ("https://sub.example.test", ("example.test",)),
            ("https://example.test", ("*",)), ("https://example.test", ("*.example",)),
            ("https://example.test", (" ",)), ("https://example.test", ("https://example.test",)),
            ("https://example.test", ("example.test/path",)), ("https://example.test", ("example.test?x",)),
            ("https://example.test", ("user@example.test",)), ("https://example.test", ("example.test\n",)),
            ("https://example.test.", ("example.test",)), ("https://example.test", ("example.test.",)),
            ("https://t\u00e9st.example", ("t\u00e9st.example",)),
            ("https://xn--tst-bma.example", ("t\u00e9st.example",)),
        )
        for url, hosts in rejected:
            with self.subTest(url=url, hosts=hosts), self.assertRaises(ProviderUnavailableError):
                validated_chat_endpoint(self.settings(url, hosts))
        self.assertEqual(validated_chat_endpoint(self.settings("https://xn--tst-bma.example", ("xn--tst-bma.example",))), "https://xn--tst-bma.example/chat/completions")

    def test_ip_allowlist_is_exact_and_ipv4_mapped_ipv6_is_rejected(self):
        self.assertEqual(validated_chat_endpoint(self.settings("https://192.0.2.1", ("192.0.2.1",))), "https://192.0.2.1/chat/completions")
        self.assertEqual(validated_chat_endpoint(self.settings("https://[2001:db8::1]", ("2001:db8::1",))), "https://[2001:db8::1]/chat/completions")
        for url, hosts in (("https://192.0.2.1", ("192.0.2.2",)), ("https://[2001:db8::1]", ("2001:db8::2",)), ("https://[::ffff:127.0.0.1]", ("::ffff:127.0.0.1",))):
            with self.subTest(url=url), self.assertRaises(ProviderUnavailableError): validated_chat_endpoint(self.settings(url, hosts))

    def test_http_is_limited_to_exact_loopback_literals_or_localhost(self):
        allowed = (("http://localhost", "localhost", "http://localhost/chat/completions"), ("http://127.0.0.1", "127.0.0.1", "http://127.0.0.1/chat/completions"), ("http://[::1]", "::1", "http://[::1]/chat/completions"), ("http://localhost:8080", "localhost", "http://localhost:8080/chat/completions"))
        for url, host, endpoint in allowed:
            with self.subTest(url=url): self.assertEqual(validated_chat_endpoint(self.settings(url, (host,))), endpoint)
        rejected = ("http://127.0.0.2", "http://0.0.0.0", "http://[::]", "http://192.168.1.1", "http://169.254.1.1", "http://[fc00::1]", "http://[fe80::1]", "http://2130706433", "http://0x7f000001", "http://127.1", "http://0177.0.0.1", "http://loopback.example")
        for url in rejected:
            host = url.split("//", 1)[1].split("/", 1)[0].strip("[]")
            with self.subTest(url=url), self.assertRaises(ProviderUnavailableError): validated_chat_endpoint(self.settings(url, (host,)))
        self.assertEqual(validated_chat_endpoint(self.settings("https://internal.example", ("internal.example",))), "https://internal.example/chat/completions")

    def test_path_policy_builds_fixed_endpoint_without_authority_replacement(self):
        expected = {
            "https://example.test": "https://example.test/chat/completions",
            "https://example.test/v1": "https://example.test/v1/chat/completions",
            "https://example.test/v1/": "https://example.test/v1/chat/completions",
            "https://example.test/v1///": "https://example.test/v1/chat/completions",
        }
        for url, endpoint in expected.items():
            with self.subTest(url=url): self.assertEqual(validated_chat_endpoint(self.settings(url)), endpoint)
        rejected = ("https://example.test/chat/completions", "https://example.test/v1/chat/completions", "https://example.test/a/../v1", "https://example.test/a/%2e%2e/v1", "https://example.test/v1%2fprivate", "https://example.test/v1%5cprivate", "https://example.test/v1\\private", "https://example.test/v1//private", "https://example.test/v1\t", "https://example.test/v1?x", "https://example.test/v1#x")
        for url in rejected:
            with self.subTest(url=url), self.assertRaises(ProviderUnavailableError): validated_chat_endpoint(self.settings(url))

    def test_comma_separated_allowlist_is_normalized_and_deduplicated(self):
        from backend.settings import _get_allowed_model_hosts
        self.assertEqual(_get_allowed_model_hosts(" example.test,EXAMPLE.TEST, ,api.example.test "), ("example.test", "api.example.test"))

    def test_public_request_schema_cannot_override_gateway_configuration(self):
        for field in ("LLM_BASE_URL", "LLM_ALLOWED_HOSTS", "provider"):
            with self.subTest(field=field), self.assertRaises(Exception):
                ChatRequest.model_validate({"question": "What is BIS?", field: "attacker-value"})


class OpenAICompatibleGeneratorTestSupport:
    def settings(self, **kwargs):
        values = dict(provider="openai_compatible", api_key="test-key", model="test-model", timeout_seconds=30, max_completion_tokens=2048, base_url="https://example.test/v1", allowed_hosts=("example.test",))
        values.update(kwargs); return GenerationSettings(**values)
    def generator(self, handler, **kwargs):
        return OpenAICompatibleGenerator(self.settings(**kwargs), httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False))
class OpenAICompatibleRequestTests(OpenAICompatibleGeneratorTestSupport, unittest.TestCase):
    def test_default_client_disables_redirect_following(self):
        with patch("backend.openai_compatible_generator.httpx.Client") as client:
            OpenAICompatibleGenerator(self.settings())
        self.assertFalse(client.call_args.kwargs["follow_redirects"])

    def test_post_payload_uses_fixed_endpoint_and_neutral_fields(self):
        seen = {}
        def handler(request):
            seen.update(method=request.method, url=str(request.url), headers=request.headers, payload=json.loads(request.content))
            return httpx.Response(200, json={"choices":[{"message":{"content":"{}"}}]})
        self.generator(handler).generate("question sentinel", [{"citation_id":"S1","text":"evidence sentinel"}])
        self.assertEqual(seen["method"], "POST"); self.assertEqual(seen["url"], "https://example.test/v1/chat/completions")
        self.assertEqual(seen["headers"]["content-type"], "application/json"); self.assertEqual(seen["headers"]["authorization"], "Bearer test-key")
        self.assertEqual(seen["payload"]["model"], "test-model"); self.assertEqual(seen["payload"]["temperature"], 0); self.assertEqual(seen["payload"]["max_completion_tokens"], 2048); self.assertFalse(seen["payload"]["stream"])
        self.assertIn("question sentinel", seen["payload"]["messages"][1]["content"]); self.assertIn("evidence sentinel", seen["payload"]["messages"][1]["content"])
        self.assertNotIn("tools", seen["payload"]); self.assertNotIn("reasoning_effort", seen["payload"]); self.assertNotIn("include_reasoning", seen["payload"])
    def test_empty_key_omits_authorization(self):
        def handler(request):
            self.assertNotIn("authorization", request.headers); return httpx.Response(200, json={"choices":[{"message":{"content":"{}"}}]})
        self.generator(handler, api_key=None).generate("q", [])
    def test_json_schema_mode_is_strict_and_closed(self):
        def handler(request):
            schema=json.loads(request.content)["response_format"]["json_schema"]; self.assertTrue(schema["strict"]); self.assertFalse(schema["schema"]["additionalProperties"]); return httpx.Response(200,json={"choices":[{"message":{"content":"{}"}}]})
        self.generator(handler).generate("q", [])
    def test_json_object_mode_is_exact(self):
        def handler(request):
            self.assertEqual(json.loads(request.content)["response_format"], {"type":"json_object"}); return httpx.Response(200,json={"choices":[{"message":{"content":"{}"}}]})
        self.generator(handler, structured_output_mode="json_object").generate("q", [])
    def test_repair_and_concise_preserve_prompt_contract(self):
        def handler(request):
            prompt=json.loads(request.content)["messages"][1]["content"]; self.assertIn("previous response was invalid",prompt); self.assertIn("feedback",prompt); self.assertIn("especially concise",prompt); return httpx.Response(200,json={"choices":[{"message":{"content":"{}"}}]})
        self.generator(handler).generate("q", [], repair=True, concise=True, repair_feedback="feedback")


class OpenAICompatibleResponseTests(OpenAICompatibleGeneratorTestSupport, unittest.TestCase):
    def test_safe_provider_request_id_is_extracted_and_logged_only_on_failure(self):
        response = httpx.Response(500, headers={"x-request-id": "provider-request-001"})
        with self.assertLogs("backend.openai_compatible_generator", level="WARNING") as captured:
            with self.assertRaises(ProviderUnavailableError):
                self.generator(lambda _: response).generate("q", [])
        self.assertIn("request_id=provider-request-001", "\n".join(captured.output))

    def test_invalid_provider_request_ids_are_rejected(self):
        invalid = ("short", "x" * 65, "contains space", "slash/id", "a:b", "a,b", "a=b", "caf\u00e9", "line\nbreak", "\u0000control")
        for value in invalid:
            with self.subTest(value=repr(value)), self.assertLogs("backend.openai_compatible_generator", level="WARNING") as captured:
                with self.assertRaises(ProviderUnavailableError):
                    headers = (
                        httpx.Headers([(b"x-request-id", value.encode("utf-8"))])
                        if value == "caf\u00e9"
                        else {"x-request-id": value}
                    )
                    self.generator(lambda _, headers=headers: httpx.Response(500, headers=headers)).generate("q", [])
            self.assertIn("request_id=None", "\n".join(captured.output))

    def test_duplicate_conflicting_and_unknown_provider_request_id_headers_are_rejected(self):
        cases = (
            [("x-request-id", "provider-request-001"), ("x-request-id", "provider-request-001")],
            [("x-request-id", "provider-request-001"), ("request-id", "provider-request-002")],
            [("x-provider-request-id", "provider-request-001")],
        )
        for headers in cases:
            with self.subTest(headers=headers), self.assertLogs("backend.openai_compatible_generator", level="WARNING") as captured:
                with self.assertRaises(ProviderUnavailableError):
                    self.generator(lambda _, headers=headers: httpx.Response(500, headers=headers)).generate("q", [])
            self.assertIn("request_id=None", "\n".join(captured.output))
    def test_valid_nonempty_content_is_extracted(self):
        self.assertEqual(self.generator(lambda _: httpx.Response(200,json={"choices":[{"message":{"content":"ok"}}]})).generate("q",[]), "ok")
    def test_missing_empty_or_nontext_content_is_rejected(self):
        for payload in ({}, {"choices":[]}, {"choices":[{}]}, {"choices":[{"message":{}}]}, {"choices":[{"message":{"content":""}}]}, {"choices":[{"message":{"content":3}}]}, {"choices":[{"message":{"tool_calls":[]}}]}):
            with self.subTest(payload=payload), self.assertRaises(ProviderResponseError): self.generator(lambda _,p=payload: httpx.Response(200,json=p)).generate("q",[])
    def test_length_finish_reason_maps_to_completion_exhaustion(self):
        with self.assertRaises(ProviderCompletionExhaustedError): self.generator(lambda _: httpx.Response(400,json={"choices":[{"finish_reason":"length"}]})).generate("q",[])
    def test_other_finish_reason_is_response_error(self):
        with self.assertRaises(ProviderResponseError): self.generator(lambda _: httpx.Response(400,json={"choices":[{"finish_reason":"stop"}]})).generate("q",[])
    def test_error_mapping_is_neutral(self):
        for code, exc in ((401,ProviderUnavailableError),(403,ProviderUnavailableError),(500,ProviderUnavailableError),(502,ProviderUnavailableError),(503,ProviderUnavailableError),(404,ProviderResponseError)):
            with self.subTest(code=code), self.assertRaises(exc): self.generator(lambda _,c=code: httpx.Response(c,json={})).generate("q",[])
    def test_rate_limit_preserves_only_numeric_retry_after(self):
        with self.assertRaises(ProviderRateLimitError) as hit: self.generator(lambda _: httpx.Response(429,headers={"Retry-After":"12"})).generate("q",[])
        self.assertEqual(hit.exception.retry_after,"12")
        with self.assertRaises(ProviderRateLimitError) as hit: self.generator(lambda _: httpx.Response(429,headers={"Retry-After":"bad"})).generate("q",[])
        self.assertIsNone(hit.exception.retry_after)
    def test_timeout_and_connection_errors_are_mapped(self):
        with self.assertRaises(ProviderTimeoutError): self.generator(lambda _: (_ for _ in ()).throw(httpx.ReadTimeout("x"))).generate("q",[])
        with self.assertRaises(ProviderUnavailableError): self.generator(lambda _: (_ for _ in ()).throw(httpx.ConnectError("x"))).generate("q",[])


class OpenAICompatibleRedirectTests(OpenAICompatibleGeneratorTestSupport, unittest.TestCase):
    def test_redirects_are_rejected_without_following_location(self):
        location = "https://redirect-target.test/private"
        for status in (300, 301, 302, 303, 307, 308):
            seen = []
            def handler(request, status=status):
                seen.append(str(request.url))
                return httpx.Response(status, headers={"Location": location}, json={"secret": location})
            with self.subTest(status=status), self.assertLogs("backend.openai_compatible_generator", level="WARNING") as captured:
                with self.assertRaises(ProviderResponseError) as hit:
                    self.generator(handler).generate("question", [])
            self.assertEqual(seen, ["https://example.test/v1/chat/completions"])
            self.assertEqual(str(hit.exception), "Generation provider rejected the request")
            self.assertNotIn(location, "\n".join(captured.output))

    def test_redirect_maps_to_existing_public_sanitized_502(self):
        from fastapi.testclient import TestClient
        from backend.main import create_app
        from tests.test_chat_api import FakeRetriever
        generator = self.generator(lambda _: httpx.Response(302, headers={"Location": "https://redirect-target.test"}))
        with TestClient(create_app(retriever_factory=FakeRetriever, generator_factory=lambda: generator)) as client:
            response = client.post("/api/chat", json={"question": "Tell me about BIS toy regulation"})
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json(), {"detail": "Chat generation failed."})


class OpenAICompatiblePrivacyTests(OpenAICompatibleGeneratorTestSupport, unittest.TestCase):
    def _assert_private_failure(self, handler, expected):
        key = "api-key-sentinel"
        question = "question-sentinel"
        evidence = [{
            "citation_id": "S1",
            "source_filename": "privacy-source.pdf",
            "page_start": 1,
            "page_end": 1,
            "text": "evidence-passage-sentinel",
        }]
        feedback = "repair-feedback-sentinel"
        sentinels = (key, question, "evidence-passage-sentinel", feedback, "raw-provider-body-sentinel", "https://redirect-location-sentinel.test/private", "invalid/provider/id-sentinel", "configured-url-sentinel.test", "private-path")
        with self.assertLogs("backend.openai_compatible_generator", level="WARNING") as captured:
            with self.assertRaises(expected) as raised:
                self.generator(handler, api_key=key, base_url="https://configured-url-sentinel.test/private-path", allowed_hosts=("configured-url-sentinel.test",)).generate(question, evidence, repair=True, repair_feedback=feedback)
        surface = "\n".join(captured.output) + str(raised.exception)
        for sentinel in sentinels:
            self.assertNotIn(sentinel, surface)
        self.assertIn("request_id=None", "\n".join(captured.output))

    def test_provider_id_is_absent_from_public_json_headers_and_application_id_is_preserved(self):
        from fastapi.testclient import TestClient
        from backend.main import create_app
        from tests.test_chat_api import FakeRetriever

        def make_generator():
            return OpenAICompatibleGenerator(
                self.settings(api_key="api-key-sentinel", base_url="https://private-provider-host.test/private-path", allowed_hosts=("private-provider-host.test",)),
                httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(500, headers={"x-request-id": "provider-request-001"}, content=b"raw-provider-body-sentinel")), follow_redirects=False),
            )

        for path in ("/api/chat", "/api/v1/chat"):
            app = create_app(retriever_factory=FakeRetriever, generator_factory=make_generator)
            with self.assertLogs("backend", level="WARNING") as captured, TestClient(app) as client:
                response = client.post(path, headers={"X-Request-ID": "application-request-001"}, json={"question": "Tell me about BIS toy regulation"})
            surface = "\n".join(captured.output) + response.text + "\n" + str(response.headers)
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.headers["x-request-id"], "application-request-001")
            self.assertIn("provider-request-001", "\n".join(captured.output))
            self.assertNotIn("provider-request-001", response.text)
            self.assertNotIn("provider-request-001", str(response.headers))
            self.assertNotIn("api-key-sentinel", surface)
            self.assertNotIn("private-provider-host.test", surface)
            self.assertNotIn("private-path", surface)
            self.assertNotIn("raw-provider-body-sentinel", surface)

    def test_no_question_evidence_repair_key_url_and_raw_body_leakage(self):
        raw = "raw-provider-body-sentinel"
        location = "https://redirect-location-sentinel.test/private"
        invalid_id = "invalid/provider/id-sentinel"
        failures = (
            ("timeout", lambda _: (_ for _ in ()).throw(httpx.ReadTimeout(raw)), ProviderTimeoutError),
            ("connection", lambda _: (_ for _ in ()).throw(httpx.ConnectError(raw)), ProviderUnavailableError),
            ("401", lambda _: httpx.Response(401, headers={"x-request-id": invalid_id}, content=raw.encode()), ProviderUnavailableError),
            ("403", lambda _: httpx.Response(403, headers={"x-request-id": invalid_id}, content=raw.encode()), ProviderUnavailableError),
            ("429", lambda _: httpx.Response(429, headers={"x-request-id": invalid_id}, content=raw.encode()), ProviderRateLimitError),
            ("500", lambda _: httpx.Response(500, headers={"x-request-id": invalid_id}, content=raw.encode()), ProviderUnavailableError),
            ("redirect", lambda _: httpx.Response(302, headers={"Location": location, "x-request-id": invalid_id}, content=raw.encode()), ProviderResponseError),
            ("malformed_json", lambda _: httpx.Response(200, headers={"x-request-id": invalid_id}, content=raw.encode()), ProviderResponseError),
            ("invalid_shape", lambda _: httpx.Response(200, headers={"x-request-id": invalid_id}, json={"private": raw}), ProviderResponseError),
            ("unexpected", lambda _: (_ for _ in ()).throw(RuntimeError(raw)), ProviderResponseError),
        )
        for name, handler, expected in failures:
            with self.subTest(name=name):
                self._assert_private_failure(handler, expected)

    def test_timeout_privacy(self):
        self._assert_private_failure(lambda _: (_ for _ in ()).throw(httpx.ReadTimeout("raw-provider-body-sentinel")), ProviderTimeoutError)

    def test_connection_privacy(self):
        self._assert_private_failure(lambda _: (_ for _ in ()).throw(httpx.ConnectError("raw-provider-body-sentinel")), ProviderUnavailableError)

    def test_authentication_error_privacy(self):
        self._assert_private_failure(lambda _: httpx.Response(401, headers={"x-request-id": "invalid/provider/id-sentinel"}, content=b"raw-provider-body-sentinel"), ProviderUnavailableError)

    def test_rate_limit_privacy(self):
        self._assert_private_failure(lambda _: httpx.Response(429, headers={"x-request-id": "invalid/provider/id-sentinel"}, content=b"raw-provider-body-sentinel"), ProviderRateLimitError)

    def test_5xx_privacy(self):
        self._assert_private_failure(lambda _: httpx.Response(500, headers={"x-request-id": "invalid/provider/id-sentinel"}, content=b"raw-provider-body-sentinel"), ProviderUnavailableError)

    def test_redirect_privacy(self):
        self._assert_private_failure(lambda _: httpx.Response(302, headers={"Location": "https://redirect-location-sentinel.test/private", "x-request-id": "invalid/provider/id-sentinel"}, content=b"raw-provider-body-sentinel"), ProviderResponseError)

    def test_malformed_response_privacy(self):
        self._assert_private_failure(lambda _: httpx.Response(200, headers={"x-request-id": "invalid/provider/id-sentinel"}, content=b"raw-provider-body-sentinel"), ProviderResponseError)

    def test_unexpected_exception_privacy(self):
        self._assert_private_failure(lambda _: (_ for _ in ()).throw(RuntimeError("raw-provider-body-sentinel")), ProviderResponseError)


class OpenAICompatibleMalformedResponseTests(OpenAICompatibleGeneratorTestSupport, unittest.TestCase):
    def test_malformed_response_shapes_are_rejected_without_body_leakage(self):
        evidence = [{
            "citation_id": "S1",
            "source_filename": "evidence-sentinel.pdf",
            "page_start": 1,
            "page_end": 1,
            "text": "evidence-sentinel",
        }]
        cases = {
            "empty_body": httpx.Response(200, content=b""),
            "json_null": httpx.Response(200, json=None),
            "json_array": httpx.Response(200, json=[]),
            "json_string": httpx.Response(200, json="body-sentinel"),
            "json_number": httpx.Response(200, json=1),
            "choices_missing": httpx.Response(200, json={}),
            "choices_null": httpx.Response(200, json={"choices": None}),
            "choices_not_list": httpx.Response(200, json={"choices": {}}),
            "choices_empty": httpx.Response(200, json={"choices": []}),
            "first_choice_not_object": httpx.Response(200, json={"choices": [None]}),
            "message_missing": httpx.Response(200, json={"choices": [{}]}),
            "message_null": httpx.Response(200, json={"choices": [{"message": None}]}),
            "message_not_object": httpx.Response(200, json={"choices": [{"message": []}]}),
            "content_missing": httpx.Response(200, json={"choices": [{"message": {}}]}),
            "content_null": httpx.Response(200, json={"choices": [{"message": {"content": None}}]}),
            "content_empty": httpx.Response(200, json={"choices": [{"message": {"content": ""}}]}),
            "content_whitespace": httpx.Response(200, json={"choices": [{"message": {"content": " \t"}}]}),
            "content_not_string": httpx.Response(200, json={"choices": [{"message": {"content": 3}}]}),
            "first_choice_invalid": httpx.Response(200, json={"choices": [{"message": {}}, {"message": {"content": "valid"}}]}),
            "invalid_unicode_body": httpx.Response(200, content=b"\xff"),
        }
        for name, response in cases.items():
            with self.subTest(name=name):
                with self.assertRaises(ProviderResponseError) as raised:
                    self.generator(lambda _, response=response: response).generate("question-sentinel", evidence)
                self.assertEqual(str(raised.exception), "Generation provider returned invalid output")
                self.assertNotIn("sentinel", str(raised.exception))

    def test_refusal_tool_and_non_text_responses_fail_closed(self):
        cases = {
            "refusal_only": {"refusal": "no", "content": None},
            "tool_only": {"tool_calls": [{"id": "call"}], "content": None},
            "function_only": {"function_call": {"name": "tool"}, "content": None},
            "structured_non_text": {"content": {"text": "no"}},
            "multimodal_parts": {"content": [{"type": "text", "text": "no"}]},
            "content_and_refusal": {"content": "text", "refusal": "no"},
            "content_and_tool_calls": {"content": "text", "tool_calls": []},
        }
        for name, message in cases.items():
            with self.subTest(name=name), self.assertRaises(ProviderResponseError) as hit:
                self.generator(lambda _, message=message: httpx.Response(200, json={"choices": [{"message": message}]})).generate("q", [])
            self.assertEqual(str(hit.exception), "Generation provider returned invalid output")

    def test_provider_authored_metadata_is_returned_only_as_raw_text(self):
        payload = {"choices": [{"message": {"content": "raw text", "citations": [{"page": 99}], "source": "provider"}}]}
        self.assertEqual(self.generator(lambda _: httpx.Response(200, json=payload)).generate("q", []), "raw text")


class OpenAICompatibleCompletionAndErrorTests(OpenAICompatibleGeneratorTestSupport, unittest.TestCase):
    def test_success_length_finish_reason_is_completion_exhaustion(self):
        response = httpx.Response(200, json={"choices": [{"finish_reason": "length", "message": {"content": "partial"}}]})
        with self.assertRaises(ProviderCompletionExhaustedError):
            self.generator(lambda _: response).generate("q", [])

    def test_non_length_success_finish_reasons_with_text_remain_compatible(self):
        for reason in ("max_tokens", "stop", None, "unknown", 3):
            with self.subTest(reason=repr(reason)):
                response = httpx.Response(200, json={"choices": [{"finish_reason": reason, "message": {"content": "valid"}}]})
                self.assertEqual(self.generator(lambda _, response=response: response).generate("q", []), "valid")

    def test_missing_success_finish_reason_with_text_remains_compatible(self):
        response = httpx.Response(200, json={"choices": [{"message": {"content": "valid"}}]})
        self.assertEqual(self.generator(lambda _: response).generate("q", []), "valid")

    def test_400_only_explicit_length_or_max_tokens_is_completion_exhaustion(self):
        for reason, expected in (("length", ProviderCompletionExhaustedError), ("max_tokens", ProviderCompletionExhaustedError), ("stop", ProviderResponseError), (None, ProviderResponseError), ("unknown", ProviderResponseError), (3, ProviderResponseError)):
            with self.subTest(reason=reason):
                response = httpx.Response(400, json={"choices": [{"finish_reason": reason}]})
                with self.assertRaises(expected) as hit:
                    self.generator(lambda _, response=response: response).generate("q", [])
                self.assertEqual(str(hit.exception), "Generation provider exhausted completion tokens" if expected is ProviderCompletionExhaustedError else "Generation provider rejected the request")

    def test_error_status_and_transport_mapping_is_neutral(self):
        statuses = ((401, ProviderUnavailableError), (403, ProviderUnavailableError), (408, ProviderResponseError), (409, ProviderResponseError), (422, ProviderResponseError), (429, ProviderRateLimitError), (500, ProviderUnavailableError), (502, ProviderUnavailableError), (503, ProviderUnavailableError), (504, ProviderUnavailableError))
        for status, expected in statuses:
            with self.subTest(status=status):
                with self.assertRaises(expected) as hit:
                    self.generator(lambda _, status=status: httpx.Response(status, content=b"body-sentinel")).generate("q", [])
                self.assertNotIn("body-sentinel", str(hit.exception))
        for error, expected in ((httpx.TimeoutException("x"), ProviderTimeoutError), (httpx.ConnectError("x"), ProviderUnavailableError), (httpx.NetworkError("x"), ProviderUnavailableError), (RuntimeError("unexpected"), ProviderResponseError)):
            with self.subTest(error=type(error).__name__), self.assertRaises(expected):
                self.generator(lambda _, error=error: (_ for _ in ()).throw(error)).generate("q", [])

    def test_retry_after_accepts_only_one_bounded_ascii_integer(self):
        cases = (([("Retry-After", "12")], "12"), ([("Retry-After", "0")], "0"), ([("Retry-After", "-1")], None), ([("Retry-After", "1.5")], None), ([("Retry-After", " 12 ")], None), ([("Retry-After", "Wed, 21 Oct 2015 07:28:00 GMT")], None), ([("Retry-After", "999999999")], None), ([("Retry-After", "12"), ("Retry-After", "13")], None))
        for headers, expected in cases:
            with self.subTest(headers=headers):
                with self.assertRaises(ProviderRateLimitError) as hit:
                    self.generator(lambda _, headers=headers: httpx.Response(429, headers=headers)).generate("q", [])
                self.assertEqual(hit.exception.retry_after, expected)
