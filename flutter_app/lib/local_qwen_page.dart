import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:llama_flutter_android/llama_flutter_android.dart';
import 'package:path_provider/path_provider.dart';

/// Local-only Qwen GGUF chat. Model weights are downloaded once and stored in
/// app-private storage; prompts are sent directly to llama.cpp on this device.
class LocalQwenPage extends StatefulWidget {
  const LocalQwenPage({super.key});

  @override
  State<LocalQwenPage> createState() => _LocalQwenPageState();
}

class _LocalQwenPageState extends State<LocalQwenPage> {
  static const _modelFileName = 'Qwen3.8-2B-Q4_K_M.gguf';
  static const _modelUrl =
      'https://huggingface.co/empero-ai/Qwen3.8-2B-Distill-GGUF/resolve/main/Qwen3.8-2B-Q4_K_M.gguf?download=true';
  static const _modelBytes = 1312000000;

  late LlamaController _controller;
  final _promptController = TextEditingController();
  final _scrollController = ScrollController();
  final List<_LocalMessage> _messages = [];
  String? _modelPath;
  String _status = 'Model not downloaded';
  String? _error;
  double _downloadProgress = 0;
  bool _downloading = false;
  bool _loading = false;
  bool _loaded = false;
  bool _generating = false;
  StreamSubscription<String>? _generation;

  @override
  void initState() {
    super.initState();
    _controller = LlamaController();
    _findExistingModel();
  }

  Future<File> _modelFile() async {
    final directory = await getApplicationSupportDirectory();
    final models = Directory('${directory.path}/models');
    if (!await models.exists()) await models.create(recursive: true);
    return File('${models.path}/$_modelFileName');
  }

  Future<void> _findExistingModel() async {
    try {
      final file = await _modelFile();
      if (!mounted) return;
      setState(() {
        _modelPath = file.path;
        _status = file.existsSync()
            ? 'GGUF file found • ready to load'
            : 'Ready to download Q4_K_M (about 1.31 GB)';
      });
    } catch (e) {
      if (mounted) setState(() => _error = 'Storage check failed: $e');
    }
  }

  Future<void> _downloadModel() async {
    if (_downloading || _loading || _generating) return;
    setState(() {
      _downloading = true;
      _downloadProgress = 0;
      _error = null;
      _status = 'Downloading model… keep the app open';
    });

    final client = http.Client();
    File? destination;
    try {
      destination = await _modelFile();
      final partial = File('${destination.path}.part');
      if (await partial.exists()) await partial.delete();
      final request = http.Request('GET', Uri.parse(_modelUrl));
      request.headers['User-Agent'] = 'Fresh-Apk1-Local-Qwen';
      final response = await client.send(request);
      if (response.statusCode != HttpStatus.ok) {
        throw HttpException('Model server returned HTTP ${response.statusCode}');
      }

      var received = 0;
      final sink = partial.openWrite();
      try {
        await for (final chunk in response.stream) {
          sink.add(chunk);
          received += chunk.length;
          if (mounted) {
            setState(() {
              _downloadProgress = (received / (response.contentLength ?? _modelBytes))
                  .clamp(0.0, 1.0);
              _status = 'Downloaded ${(received / 1000000000).toStringAsFixed(2)} GB';
            });
          }
        }
      } finally {
        await sink.flush();
        await sink.close();
      }

      if (received < 1000000000) {
        throw const FormatException(
          'Downloaded file is unexpectedly small; it may be an HTML error page.',
        );
      }
      if (await destination.exists()) await destination.delete();
      await partial.rename(destination.path);
      if (!mounted) return;
      setState(() {
        _modelPath = destination!.path;
        _downloadProgress = 1;
        _status = 'Download complete • load the model to start offline chat';
      });
    } catch (e) {
      if (mounted) {
        setState(() {
          _error = 'Download failed: $e';
          _status = 'Model not ready';
        });
      }
    } finally {
      client.close();
      if (mounted) setState(() => _downloading = false);
    }
  }

  Future<void> _loadModel() async {
    if (_loading || _loaded || _modelPath == null) return;
    final file = File(_modelPath!);
    if (!await file.exists() || await file.length() < 1000000000) {
      setState(() => _error = 'Model file is missing or incomplete. Download it again.');
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
      _status = 'Loading model into memory…';
    });
    try {
      // Start with a conservative context to reduce memory pressure on phones.
      await _controller.loadModel(
        modelPath: file.path,
        threads: 4,
        contextSize: 2048,
      );
      if (!mounted) return;
      setState(() {
        _loaded = true;
        _status = 'Loaded • inference runs locally on this phone';
      });
    } catch (e) {
      if (mounted) {
        setState(() {
          _error = 'Model load failed: $e. This build may not support this GGUF architecture or the phone may lack free RAM.';
          _status = 'Model not loaded';
        });
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _sendPrompt() async {
    final prompt = _promptController.text.trim();
    if (!_loaded || _generating || prompt.isEmpty) return;
    _promptController.clear();
    final assistant = _LocalMessage(isUser: false, text: '');
    setState(() {
      _messages.add(_LocalMessage(isUser: true, text: prompt));
      _messages.add(assistant);
      _generating = true;
      _error = null;
      _status = 'Generating locally…';
    });
    _scrollToBottom();

    try {
      final history = _messages
          .where((message) => message.text.isNotEmpty)
          .toList();
      final chatMessages = <ChatMessage>[
        const ChatMessage(
          role: 'system',
          content: 'You are Fresh Local Qwen, a concise assistant. For trading questions, use only facts supplied in the prompt, state uncertainty, and never invent live prices or claim an unverified trade is safe.',
        ),
        for (final message in history)
          ChatMessage(
            role: message.isUser ? 'user' : 'assistant',
            content: message.text,
          ),
      ];
      _generation = _controller
          .generateChat(
            messages: chatMessages,
            template: 'chatml',
            temperature: 0.6,
            topP: 0.95,
            topK: 20,
            maxTokens: 512,
          )
          .listen(
            (token) {
              if (!mounted) return;
              setState(() {
                assistant.text += token;
                _status = 'Generating locally…';
              });
              _scrollToBottom();
            },
            onError: (Object error) {
              if (mounted) setState(() => _error = 'Inference failed: $error');
            },
          );
      await _generation!.asFuture<void>();
      if (mounted) setState(() => _status = 'Ready • local inference');
    } catch (e) {
      if (mounted) setState(() => _error = 'Inference failed: $e');
    } finally {
      await _generation?.cancel();
      _generation = null;
      if (mounted) setState(() => _generating = false);
    }
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 180),
          curve: Curves.easeOut,
        );
      }
    });
  }

  @override
  void dispose() {
    unawaited(_generation?.cancel());
    _promptController.dispose();
    _scrollController.dispose();
    if (_loaded) unawaited(_controller.dispose());
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final canDownload = !_downloading && !_loading && !_generating;
    return ListView(
      padding: const EdgeInsets.all(12),
      children: [
        const Text(
          'LOCAL QWEN • OFFLINE AI',
          style: TextStyle(fontSize: 18, fontWeight: FontWeight.w900),
        ),
        const SizedBox(height: 6),
        const Text(
          'Qwen3.8-2B Distill GGUF • Q4_K_M • llama.cpp native inference',
          style: TextStyle(color: Colors.white70),
        ),
        const SizedBox(height: 12),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(children: [
                  Icon(
                    _loaded ? Icons.verified : Icons.memory,
                    color: _loaded ? Colors.greenAccent : Colors.cyanAccent,
                  ),
                  const SizedBox(width: 8),
                  Expanded(child: Text(_status)),
                ]),
                if (_downloading) ...[
                  const SizedBox(height: 12),
                  LinearProgressIndicator(value: _downloadProgress),
                  const SizedBox(height: 4),
                  Text('${(_downloadProgress * 100).toStringAsFixed(1)}%'),
                ],
                const SizedBox(height: 12),
                if (!_loaded)
                  Wrap(spacing: 8, runSpacing: 8, children: [
                    OutlinedButton.icon(
                      onPressed: canDownload ? _downloadModel : null,
                      icon: const Icon(Icons.download),
                      label: Text(_modelPath == null ||
                              !File(_modelPath!).existsSync()
                          ? 'Download model (~1.31 GB)'
                          : 'Download again'),
                    ),
                    FilledButton.icon(
                      onPressed: canDownload &&
                              _modelPath != null &&
                              File(_modelPath!).existsSync()
                          ? _loadModel
                          : null,
                      icon: const Icon(Icons.memory),
                      label: const Text('Load model'),
                    ),
                  ]),
                if (_loaded)
                  OutlinedButton.icon(
                    onPressed: _generating
                        ? null
                        : () async {
                            await _controller.dispose();
                            if (mounted) {
                              setState(() {
                                _controller = LlamaController();
                                _loaded = false;
                                _status = 'Model unloaded';
                              });
                            }
                          },
                    icon: const Icon(Icons.stop_circle_outlined),
                    label: const Text('Unload model'),
                  ),
                if (_error != null) ...[
                  const SizedBox(height: 10),
                  Text(_error!, style: const TextStyle(color: Colors.redAccent)),
                ],
              ],
            ),
          ),
        ),
        const Card(
          child: Padding(
            padding: EdgeInsets.all(12),
            child: Text(
              'Privacy: prompts are processed by the on-device engine. The first model download requires internet; after download, chat can work offline. The model does not provide live market data by itself. Keep at least 2 GB free and close other apps if loading fails.',
              style: TextStyle(color: Colors.white70, fontSize: 12),
            ),
          ),
        ),
        const Padding(
          padding: EdgeInsets.fromLTRB(4, 16, 4, 8),
          child: Text('LOCAL CHAT', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w800)),
        ),
        Container(
          constraints: const BoxConstraints(minHeight: 180, maxHeight: 380),
          child: ListView.builder(
            controller: _scrollController,
            shrinkWrap: true,
            itemCount: _messages.length,
            itemBuilder: (context, index) {
              final message = _messages[index];
              return Align(
                alignment: message.isUser
                    ? Alignment.centerRight
                    : Alignment.centerLeft,
                child: Card(
                  color: message.isUser
                      ? const Color(0xFF123447)
                      : const Color(0xFF101722),
                  child: Padding(
                    padding: const EdgeInsets.all(10),
                    child: SelectableText(
                      message.text.isEmpty && _generating
                          ? 'Thinking…'
                          : message.text,
                    ),
                  ),
                ),
              );
            },
          ),
        ),
        const SizedBox(height: 8),
        Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
          Expanded(
            child: TextField(
              controller: _promptController,
              minLines: 1,
              maxLines: 4,
              enabled: _loaded && !_generating,
              decoration: const InputDecoration(
                labelText: 'Ask local Qwen',
                hintText: 'No live prices unless you provide the data',
              ),
              onSubmitted: (_) => _sendPrompt(),
            ),
          ),
          const SizedBox(width: 8),
          IconButton.filled(
            onPressed: _loaded && !_generating ? _sendPrompt : null,
            tooltip: 'Send prompt',
            icon: const Icon(Icons.send),
          ),
          if (_generating)
            IconButton(
              onPressed: () async {
                await _controller.stop();
                await _generation?.cancel();
                if (mounted) setState(() => _generating = false);
              },
              tooltip: 'Stop generation',
              icon: const Icon(Icons.stop),
            ),
        ]),
      ],
    );
  }
}

class _LocalMessage {
  _LocalMessage({required this.isUser, required this.text});
  final bool isUser;
  String text;
}
