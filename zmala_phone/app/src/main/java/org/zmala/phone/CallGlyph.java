package org.zmala.phone;

import android.graphics.*;
import android.graphics.drawable.Drawable;

// @llr LLR-AND-UI-002
/** Small original line icons, drawn in a consistent 24-unit coordinate system. */
final class CallGlyph extends Drawable {
  enum Kind {
    MIC,
    SPEAKER,
    EARPIECE,
    SILENT,
    CAMERA,
    END,
    PHONE
  }

  private final Kind kind;
  private final boolean active;
  private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);

  CallGlyph(Kind kind, boolean active) {
    this.kind = kind;
    this.active = active;
    paint.setColor(Color.WHITE);
    paint.setStyle(Paint.Style.STROKE);
    paint.setStrokeWidth(1.8f);
    paint.setStrokeCap(Paint.Cap.ROUND);
    paint.setStrokeJoin(Paint.Join.ROUND);
  }

  @Override
  public void draw(Canvas canvas) {
    canvas.save();
    Rect b = getBounds();
    canvas.translate(b.left, b.top);
    canvas.scale(b.width() / 24f, b.height() / 24f);
    Path path = new Path();
    switch (kind) {
      case MIC:
        canvas.drawRoundRect(9, 2, 15, 14, 3, 3, paint);
        canvas.drawArc(6, 6, 18, 18, 0, 180, false, paint);
        canvas.drawLine(12, 18, 12, 22, paint);
        canvas.drawLine(8, 22, 16, 22, paint);
        if (active) canvas.drawLine(3, 3, 21, 21, paint);
        break;
      case SPEAKER:
        path.moveTo(3, 9);
        path.lineTo(7, 9);
        path.lineTo(12, 5);
        path.lineTo(12, 19);
        path.lineTo(7, 15);
        path.lineTo(3, 15);
        path.close();
        canvas.drawPath(path, paint);
        {
          canvas.drawArc(10, 7, 20, 17, -60, 120, false, paint);
          canvas.drawArc(8, 3, 24, 21, -55, 110, false, paint);
        }
        break;
      case EARPIECE:
        canvas.drawRoundRect(7, 2, 17, 22, 2, 2, paint);
        canvas.drawLine(10, 5, 14, 5, paint);
        canvas.drawCircle(12, 19, .6f, paint);
        break;
      case SILENT:
        path.moveTo(3, 9); path.lineTo(7, 9); path.lineTo(12, 5);
        path.lineTo(12, 19); path.lineTo(7, 15); path.lineTo(3, 15); path.close();
        canvas.drawPath(path, paint);
        canvas.drawLine(17, 10, 21, 14, paint);
        canvas.drawLine(17, 14, 21, 10, paint);
        break;
      case CAMERA:
        canvas.drawRoundRect(3, 6, 21, 18, 2, 2, paint);
        canvas.drawArc(8, 8, 16, 16, 35, 280, false, paint);
        path.moveTo(16, 8);
        path.lineTo(16, 11);
        path.lineTo(13, 10);
        canvas.drawPath(path, paint);
        break;
      case END:
      case PHONE:
        if (kind == Kind.PHONE) canvas.rotate(-125, 12, 12);
        path.moveTo(3, 16);
        path.lineTo(3, 12);
        path.cubicTo(7, 7, 17, 7, 21, 12);
        path.lineTo(21, 16);
        path.lineTo(16, 15);
        path.lineTo(16, 12);
        path.quadTo(12, 10, 8, 12);
        path.lineTo(8, 15);
        path.close();
        canvas.drawPath(path, paint);
        break;
    }
    canvas.restore();
  }

  @Override
  public void setAlpha(int alpha) {
    paint.setAlpha(alpha);
    invalidateSelf();
  }

  @Override
  public void setColorFilter(ColorFilter filter) {
    paint.setColorFilter(filter);
    invalidateSelf();
  }

  @Override
  public int getOpacity() {
    return PixelFormat.TRANSLUCENT;
  }

  @Override
  public int getIntrinsicWidth() {
    return 24;
  }

  @Override
  public int getIntrinsicHeight() {
    return 24;
  }
}
