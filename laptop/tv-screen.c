// tv-screen: plug a virtual monitor into the first evdi device until stopped.
// The desktop sees a normal monitor (from the EDID file), so windows can be moved onto it,
// and Sunshine streams it to the TV. Stopping (SIGTERM or SIGINT) unplugs it again.
// evdi doesn't finish a display update until a client has collected the frame, and without
// that the X server stalls ("flip_done timed out"), so every frame is grabbed and discarded.
// Build: gcc -O2 -Wall -o laptop/tv-screen laptop/tv-screen.c -levdi
// Usage: laptop/tv-screen laptop/tv-screen-1080p.edid
#include <stdint.h> // before evdi_lib.h, which uses its types without including it
#include <evdi_lib.h>
#include <poll.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>

#define BUFFER_ID 1
#define MAX_RECTS 16

static volatile sig_atomic_t stop;
static evdi_handle handle = EVDI_INVALID_HANDLE;
static unsigned char *pixels;
static struct evdi_rect rects[MAX_RECTS];

static void on_signal(int sig) { (void)sig; stop = 1; }

static void grab(void)
{
	int num_rects = MAX_RECTS;

	evdi_grab_pixels(handle, rects, &num_rects);
}

// Ask for the next frame, collecting any that are ready straight away
static void request_frames(void)
{
	while (pixels && evdi_request_update(handle, BUFFER_ID))
		grab();
}

static void on_update_ready(int buffer_id, void *user_data)
{
	(void)buffer_id;
	(void)user_data;
	grab();
	request_frames();
}

static void on_mode(struct evdi_mode mode, void *user_data)
{
	(void)user_data;
	printf("mode set: %dx%d at %d Hz\n", mode.width, mode.height, mode.refresh_rate);
	fflush(stdout);

	if (pixels) {
		evdi_unregister_buffer(handle, BUFFER_ID);
		free(pixels);
	}
	int stride = mode.width * (mode.bits_per_pixel / 8);
	pixels = malloc((size_t)stride * mode.height);
	if (!pixels) {
		perror("malloc");
		stop = 1;
		return;
	}
	struct evdi_buffer buffer = {
		.id = BUFFER_ID, .buffer = pixels, .width = mode.width, .height = mode.height,
		.stride = stride, .rects = rects, .rect_count = 0,
	};
	evdi_register_buffer(handle, buffer);
	request_frames();
}

static void on_dpms(int dpms_mode, void *user_data)
{
	(void)user_data;
	printf("dpms: %d\n", dpms_mode);
	fflush(stdout);
}

int main(int argc, char **argv)
{
	unsigned char edid[512];
	size_t edid_len;
	FILE *f;
	int device;

	if (argc != 2) {
		fprintf(stderr, "usage: %s EDID-FILE\n", argv[0]);
		return 2;
	}
	f = fopen(argv[1], "rb");
	if (!f) {
		perror(argv[1]);
		return 1;
	}
	edid_len = fread(edid, 1, sizeof(edid), f);
	fclose(f);
	if (edid_len < 128 || edid_len % 128) {
		fprintf(stderr, "%s: not an EDID (%zu bytes)\n", argv[1], edid_len);
		return 1;
	}

	for (device = 0; device < 32; device++) {
		if (evdi_check_device(device) == AVAILABLE) {
			handle = evdi_open(device);
			break;
		}
	}
	if (handle == EVDI_INVALID_HANDLE) {
		fprintf(stderr, "no evdi device found (is the evdi module loaded with a device?)\n");
		return 1;
	}

	signal(SIGTERM, on_signal);
	signal(SIGINT, on_signal);

	// Limits only need to allow the EDID's largest mode: 3840x2160 at 60 Hz
	evdi_connect(handle, edid, (unsigned int)edid_len, 3840 * 2160, 3840 * 2160 * 60);
	printf("plugged in on /dev/dri/card%d\n", device);
	fflush(stdout);

	struct evdi_event_context ctx = {
		.mode_changed_handler = on_mode,
		.update_ready_handler = on_update_ready,
		.dpms_handler = on_dpms,
	};
	struct pollfd pfd = { .fd = evdi_get_event_ready(handle), .events = POLLIN };

	while (!stop) {
		if (poll(&pfd, 1, 1000) > 0)
			evdi_handle_events(handle, &ctx);
	}

	if (pixels) {
		evdi_unregister_buffer(handle, BUFFER_ID);
		free(pixels);
	}
	evdi_disconnect(handle);
	evdi_close(handle);
	printf("unplugged\n");
	return 0;
}
